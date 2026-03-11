import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY") ?? "";
const SUPABASE_URL      = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY") ?? "";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, anthropic-version, anthropic-beta, x-api-key",
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

  // Validate caller's Supabase JWT
  const jwt = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
  if (!jwt) {
    return new Response(JSON.stringify({ error: "Missing Authorization header" }), {
      status: 401, headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    global: { headers: { Authorization: `Bearer ${jwt}` } },
  });
  const { data: { user }, error } = await supabase.auth.getUser();
  if (error || !user) {
    return new Response(JSON.stringify({ error: "Invalid or expired session" }), {
      status: 401, headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  // Build upstream path — strip the edge function prefix
  const url = new URL(req.url);
  const path = url.pathname.replace(/^\/functions\/v1\/claude-proxy/, "") || "/v1/messages";

  const body = await req.text();

  // Forward to Anthropic with the real key
  const upstreamHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": req.headers.get("anthropic-version") ?? "2023-06-01",
  };
  const betaHeader = req.headers.get("anthropic-beta");
  if (betaHeader) upstreamHeaders["anthropic-beta"] = betaHeader;

  const upstream = await fetch(`https://api.anthropic.com${path}`, {
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
