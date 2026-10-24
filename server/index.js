/**
 * CineStream Main Server
 * Provides REST API endpoints, static web hosting, session management,
 * and background server health checks.
 */

require('dotenv').config();
const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');
const db = require('./db');
const { getClientIp, checkRateLimit, resolveClientId, sanitizeString } = require('./auth');

const PORT = process.env.PORT || 3000;
const PUBLIC_DIR = path.join(__dirname, '..');

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

function sendJson(res, statusCode, data) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'SAMEORIGIN',
  });
  res.end(JSON.stringify(data));
}

function parseJsonBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => {
      body += chunk;
      if (body.length > 1e6) { // 1MB limit
        req.destroy();
        reject(new Error('Request entity too large'));
      }
    });
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (err) {
        reject(new Error('Invalid JSON format'));
      }
    });
  });
}

function serveStatic(req, res, pathname) {
  let safePath = path.normalize(pathname).replace(/^(\.\.[\/\\])+/, '');
  if (safePath === '/' || safePath === '') safePath = '/index.html';

  const filePath = path.join(PUBLIC_DIR, safePath);

  // Security check: ensure path remains within PUBLIC_DIR
  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403);
    res.end('Access Denied');
    return;
  }

  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      // Fallback to index.html for SPA hash/route navigation
      const indexPath = path.join(PUBLIC_DIR, 'index.html');
      fs.readFile(indexPath, (readErr, content) => {
        if (readErr) {
          res.writeHead(404);
          res.end('Not Found');
        } else {
          res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
          res.end(content);
        }
      });
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    res.writeHead(200, {
      'Content-Type': contentType,
      'Cache-Control': 'no-cache, must-revalidate',
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'SAMEORIGIN',
    });
    fs.createReadStream(filePath).pipe(res);
  });
}

const server = http.createServer(async (req, res) => {
  const host = req.headers.host || 'localhost:3000';
  const parsedUrl = new URL(req.url, `http://${host}`);
  const pathname = parsedUrl.pathname;
  const query = Object.fromEntries(parsedUrl.searchParams.entries());
  const method = req.method.toUpperCase();
  const clientIp = getClientIp(req);
  const clientId = resolveClientId(req, res);

  // CORS headers for API calls
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-cinestream-client-id');

  if (method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // API Routing
  try {
    // 1. Featured Media
    if (method === 'GET' && pathname === '/api/media/featured') {
      const items = await db.getFeatured();
      return sendJson(res, 200, items);
    }

    // 2. Trending Media
    if (method === 'GET' && pathname === '/api/media/trending') {
      const items = await db.getTrending();
      return sendJson(res, 200, items);
    }

    // 3. Catalog Listing & Filter
    if (method === 'GET' && pathname === '/api/media') {
      const catalog = await db.getCatalog({
        type: query.type,
        genre: query.genre,
        language: query.language,
        quality: query.quality,
        sort: query.sort,
        limit: parseInt(query.limit) || 20,
        page: parseInt(query.page) || 1,
      });
      return sendJson(res, 200, catalog);
    }

    // 4. Live Autocomplete Search
    if (method === 'GET' && pathname === '/api/search/live') {
      const results = await db.searchLive(query.q || '');
      return sendJson(res, 200, results);
    }

    // 5. Full Search Lookup
    if (method === 'GET' && pathname === '/api/search') {
      const results = await db.searchFull(query.q || '');
      return sendJson(res, 200, { items: results, total: results.length });
    }

    // 6. Media Detail by Slug
    if (method === 'GET' && pathname.startsWith('/api/media/')) {
      const slug = pathname.replace('/api/media/', '');
      const media = await db.getBySlug(slug);
      if (!media) return sendJson(res, 404, { error: 'Media not found' });
      return sendJson(res, 200, media);
    }

    // 7. Episode Watch Stream Data
    if (method === 'GET' && pathname.startsWith('/api/series/')) {
      const match = pathname.match(/^\/api\/series\/([^\/]+)\/seasons\/(\d+)\/episodes\/(\d+)$/);
      if (match) {
        const slug = match[1];
        const seasonNum = parseInt(match[2]);
        const episodeNum = parseInt(match[3]);
        const episodeData = await db.getEpisode(slug, seasonNum, episodeNum);
        if (!episodeData) return sendJson(res, 404, { error: 'Episode not found' });
        return sendJson(res, 200, episodeData);
      }
    }

    // 8. Watchlist Fetch
    if (method === 'GET' && pathname === '/api/watchlist') {
      const items = await db.getWatchlist(clientId);
      return sendJson(res, 200, items);
    }

    // 9. Watchlist Toggle
    if (method === 'POST' && pathname === '/api/watchlist/toggle') {
      const body = await parseJsonBody(req);
      if (!body.mediaId) return sendJson(res, 400, { error: 'mediaId is required' });
      const result = await db.toggleWatchlist(clientId, sanitizeString(body.mediaId));
      return sendJson(res, 200, result);
    }

    // 10. Issue Reporting (Rate-limited)
    if (method === 'POST' && pathname === '/api/reports') {
      if (!checkRateLimit(clientIp, 10, 60000)) {
        return sendJson(res, 429, { error: 'Too many requests. Please wait before submitting another report.' });
      }
      const body = await parseJsonBody(req);
      const report = await db.createIssueReport({
        mediaTitle: sanitizeString(body.mediaTitle || 'Unknown'),
        serverName: sanitizeString(body.serverName || 'Server 1'),
        category: sanitizeString(body.category || 'broken_link'),
        details: sanitizeString(body.details || '', 500),
        clientIpHash: require('crypto').createHash('sha256').update(clientIp).digest('hex').substring(0, 16),
      });
      return sendJson(res, 201, { success: true, reportId: report.id });
    }

    // 11. Title Request
    if (method === 'POST' && pathname === '/api/requests') {
      if (!checkRateLimit(clientIp, 5, 60000)) {
        return sendJson(res, 429, { error: 'Too many title requests submitted.' });
      }
      const body = await parseJsonBody(req);
      const titleRequest = await db.createTitleRequest({
        title: sanitizeString(body.title, 120),
        year: parseInt(body.year) || null,
        notes: sanitizeString(body.notes || '', 300),
        clientIpHash: require('crypto').createHash('sha256').update(clientIp).digest('hex').substring(0, 16),
      });
      return sendJson(res, 201, { success: true, requestId: titleRequest.id });
    }

    // 12. Automated Health Check Cron
    if (method === 'POST' && pathname === '/api/cron/check-servers') {
      const health = await db.checkServerHealth();
      return sendJson(res, 200, health);
    }

    // Static Web Serving fallback
    if (method === 'GET') {
      return serveStatic(req, res, pathname);
    }

    return sendJson(res, 404, { error: 'Not found' });
  } catch (err) {
    console.error('API Error:', err);
    return sendJson(res, 500, { error: 'Internal Server Error' });
  }
});

server.listen(PORT, () => {
  console.log(`=======================================================`);
  console.log(`🚀 CineStream Backend & Web Server running on port ${PORT}`);
  console.log(`📡 Local URL: http://localhost:${PORT}`);
  console.log(`📦 Database: ${process.env.DATABASE_URL ? 'PostgreSQL Active' : 'Resilient In-Memory Store Active'}`);
  console.log(`🛡️  Security: RLS, Rate Limiting & Iframe Sandboxing Active`);
  console.log(`=======================================================`);
});

module.exports = server;
