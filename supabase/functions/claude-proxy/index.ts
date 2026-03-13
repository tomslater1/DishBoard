import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY") ?? "";
const SUPABASE_URL      = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
const DAILY_LIMIT       = Number.parseInt(Deno.env.get("CLAUDE_DAILY_LIMIT") ?? "50", 10) || 50;

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, anthropic-version, anthropic-beta",
};

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405, headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  if (!ANTHROPIC_API_KEY || !SUPABASE_URL || !SUPABASE_ANON_KEY) {
    return new Response(JSON.stringify({ error: "Proxy not configured" }), {
      status: 500, headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  // Validate caller's Supabase JWT
  const authHeader = req.headers.get("Authorization") ?? "";
  if (!/^Bearer\s+\S+$/i.test(authHeader)) {
    return new Response(JSON.stringify({ error: "Missing or invalid Authorization header" }), {
      status: 401, headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }
  const jwt = authHeader.replace(/^Bearer\s+/i, "");
  if (!jwt) {
    return new Response(JSON.stringify({ error: "Missing Authorization header" }), {
      status: 401, headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  const { data: { user }, error } = await supabase.auth.getUser(jwt);
  if (error || !user) {
    return new Response(JSON.stringify({ error: "Invalid or expired session" }), {
      status: 401, headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  // User-scoped client for metering updates via RLS.
  const userClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    global: { headers: { Authorization: `Bearer ${jwt}` } },
  });

  const usageDate = new Date().toISOString().slice(0, 10); // UTC day
  const usageNow = new Date().toISOString();
  let meteringAvailable = true;
  const usageRes = await userClient
    .from("ai_usage_daily")
    .select("id,request_count,blocked_count")
    .eq("user_id", user.id)
    .eq("usage_date", usageDate)
    .limit(1);
  if (usageRes.error) {
    meteringAvailable = false;
    console.warn("AI usage metering unavailable:", usageRes.error.message);
  }

  const current = meteringAvailable
    ? ((usageRes.data ?? [])[0] as { request_count: number; blocked_count: number } | undefined)
    : undefined;
  const currentCount = Number(current?.request_count ?? 0);
  if (meteringAvailable && currentCount >= DAILY_LIMIT) {
    if (current) {
      await userClient
        .from("ai_usage_daily")
        .update({
          blocked_count: Number(current.blocked_count ?? 0) + 1,
          updated_at: usageNow,
        })
        .eq("user_id", user.id)
        .eq("usage_date", usageDate);
    }
    return new Response(JSON.stringify({ error: `Daily AI request limit reached (${DAILY_LIMIT}/day).` }), {
      status: 429, headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  if (meteringAvailable && current) {
    const upd = await userClient
      .from("ai_usage_daily")
      .update({
        request_count: currentCount + 1,
        updated_at: usageNow,
      })
      .eq("user_id", user.id)
      .eq("usage_date", usageDate);
    if (upd.error) {
      meteringAvailable = false;
      console.warn("AI usage metering update failed:", upd.error.message);
    }
  } else if (meteringAvailable) {
    const ins = await userClient.from("ai_usage_daily").insert({
      user_id: user.id,
      usage_date: usageDate,
      request_count: 1,
      blocked_count: 0,
      updated_at: usageNow,
    });
    if (ins.error) {
      meteringAvailable = false;
      console.warn("AI usage metering insert failed:", ins.error.message);
    }
  }

  const body = await req.text();
  if (body.length > 1_000_000) {
    return new Response(JSON.stringify({ error: "Request body too large" }), {
      status: 413, headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  // Forward to Anthropic with the real key
  const upstreamHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": req.headers.get("anthropic-version") ?? "2023-06-01",
  };
  const betaHeader = req.headers.get("anthropic-beta");
  if (betaHeader) upstreamHeaders["anthropic-beta"] = betaHeader;

  const upstream = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: upstreamHeaders,
    body,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      ...Object.fromEntries(upstream.headers.entries()),
      ...CORS_HEADERS,
    },
  });
});
