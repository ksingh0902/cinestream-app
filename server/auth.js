/**
 * Authentication, Session & Rate Limiting Middleware
 */

const crypto = require('crypto');

// In-memory sliding window rate limiter
const rateLimits = new Map();

function getClientIp(req) {
  return req.headers['x-forwarded-for'] ||
         req.connection.remoteAddress ||
         req.socket.remoteAddress ||
         '127.0.0.1';
}

function checkRateLimit(ip, limit = 60, windowMs = 60000) {
  const now = Date.now();
  let record = rateLimits.get(ip);

  if (!record || now - record.startTime > windowMs) {
    record = { startTime: now, count: 1 };
    rateLimits.set(ip, record);
    return true;
  }

  record.count += 1;
  return record.count <= limit;
}

function parseCookies(req) {
  const list = {};
  const rc = req.headers.cookie;

  if (rc) {
    rc.split(';').forEach(cookie => {
      const parts = cookie.split('=');
      list[parts.shift().trim()] = decodeURI(parts.join('='));
    });
  }
  return list;
}

function resolveClientId(req, res) {
  const cookies = parseCookies(req);
  let clientId = req.headers['x-cinestream-client-id'] || cookies['cinestream_client_id'];

  if (!clientId) {
    clientId = crypto.randomUUID();
    res.setHeader('Set-Cookie', `cinestream_client_id=${clientId}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000`);
  }
  return clientId;
}

function sanitizeString(str, maxLength = 255) {
  if (typeof str !== 'string') return '';
  return str.trim().slice(0, maxLength).replace(/<[^>]*>?/gm, '');
}

module.exports = {
  getClientIp,
  checkRateLimit,
  resolveClientId,
  sanitizeString,
};
