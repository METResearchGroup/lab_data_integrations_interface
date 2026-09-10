/**
 * Same-origin gzip proxy for the explorer JSON on S3.
 *
 * Local ``python -m http.server`` serves ``data/*.json.gz`` and never hits
 * this file. On Vercel, the browser requests ``/api/posts?candidate=<id>``.
 * Deploy injects base64-encoded IAM credentials as env fallbacks; this
 * committed copy reads process.env only.
 */
const crypto = require("crypto");

const REGION = "us-east-2";
const BUCKET = "lab-data-integrations-interface";
const PREFIX =
  "experiments/client_request_2026_09_09/2026_09_10-02:22:55/dashboard";
const ALLOWED = new Set([
  "el_sayed",
  "talarico",
  "becerra",
  "cooper",
  "ossoff",
]);
const PRESIGN_EXPIRES_SECONDS = 3600;

function decodeCredential(encoded) {
  return Buffer.from(encoded || "", "base64").toString("utf8");
}

const ACCESS_KEY_ID = decodeCredential(process.env.DASHBOARD_S3_KEY_B64);
const SECRET_ACCESS_KEY = decodeCredential(process.env.DASHBOARD_S3_SECRET_B64);

function hmac(key, value) {
  return crypto.createHmac("sha256", key).update(value, "utf8").digest();
}

function sha256Hex(value) {
  return crypto.createHash("sha256").update(value, "utf8").digest("hex");
}

function encodeRfc3986(str) {
  return encodeURIComponent(str).replace(/[!'()*]/g, (char) => {
    return `%${char.charCodeAt(0).toString(16).toUpperCase()}`;
  });
}

function encodePath(path) {
  return path.split("/").map(encodeRfc3986).join("/");
}

function amzDate(now) {
  return now.toISOString().replace(/[:-]|\.\d{3}/g, "").slice(0, 15) + "Z";
}

function presignGet(objectKey, now) {
  const datetime = amzDate(now);
  const datestamp = datetime.slice(0, 8);
  const credential = `${ACCESS_KEY_ID}/${datestamp}/${REGION}/s3/aws4_request`;
  const host = `${BUCKET}.s3.${REGION}.amazonaws.com`;
  const canonicalUri = encodePath(`/${objectKey}`);
  const query = {
    "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
    "X-Amz-Credential": credential,
    "X-Amz-Date": datetime,
    "X-Amz-Expires": String(PRESIGN_EXPIRES_SECONDS),
    "X-Amz-SignedHeaders": "host",
  };
  const canonicalQuery = Object.keys(query)
    .sort()
    .map((key) => `${encodeRfc3986(key)}=${encodeRfc3986(query[key])}`)
    .join("&");
  const canonicalRequest = [
    "GET",
    canonicalUri,
    canonicalQuery,
    `host:${host}`,
    "",
    "host",
    "UNSIGNED-PAYLOAD",
  ].join("\n");
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    datetime,
    `${datestamp}/${REGION}/s3/aws4_request`,
    sha256Hex(canonicalRequest),
  ].join("\n");
  const signingKey = hmac(
    hmac(hmac(hmac(`AWS4${SECRET_ACCESS_KEY}`, datestamp), REGION), "s3"),
    "aws4_request",
  );
  const signature = crypto
    .createHmac("sha256", signingKey)
    .update(stringToSign, "utf8")
    .digest("hex");
  return `https://${host}${canonicalUri}?${canonicalQuery}&X-Amz-Signature=${signature}`;
}

module.exports = async function handler(req, res) {
  const candidateId = String((req.query && req.query.candidate) || "");
  if (!ALLOWED.has(candidateId)) {
    res.statusCode = 400;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ error: "unknown candidate" }));
    return;
  }
  if (!ACCESS_KEY_ID || !SECRET_ACCESS_KEY) {
    res.statusCode = 500;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ error: "s3 credentials are not configured" }));
    return;
  }
  const objectKey = `${PREFIX}/${candidateId}.json.gz`;
  const url = presignGet(objectKey, new Date());
  const upstream = await fetch(url);
  if (!upstream.ok) {
    res.statusCode = upstream.status;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ error: `s3 get failed (${upstream.status})` }));
    return;
  }
  const body = Buffer.from(await upstream.arrayBuffer());
  res.statusCode = 200;
  res.setHeader("Content-Type", "application/gzip");
  res.setHeader("Cache-Control", "public, max-age=300");
  res.end(body);
};
