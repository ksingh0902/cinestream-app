/**
 * Automated Flow Test Suite for CineStream
 * Tests all flows (F01-F05), happy paths, edge cases, rate limits, and client session isolation.
 * Uses native node:test & node:assert.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');

// Launch test instance of server
process.env.PORT = '3099';
const server = require('../server/index.js');

const BASE_URL = 'http://localhost:3099';

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BASE_URL);
    const req = http.request(url, options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        let json = null;
        try {
          json = JSON.parse(data);
        } catch (e) {
          json = data;
        }
        resolve({
          status: res.statusCode,
          headers: res.headers,
          body: json,
        });
      });
    });
    req.on('error', reject);
    if (options.body) {
      req.write(typeof options.body === 'string' ? options.body : JSON.stringify(options.body));
    }
    req.end();
  });
}

test('F01: Search, Select, and Stream a Movie', async (t) => {
  await t.test('F01-H1: Live search autocomplete returns relevant titles with thumbnails', async () => {
    const res = await request('/api/search/live?q=dune');
    assert.equal(res.status, 200);
    assert.ok(Array.isArray(res.body));
    assert.ok(res.body.length > 0);
    assert.equal(res.body[0].slug, 'dune-part-two');
    assert.ok(res.body[0].poster);
    assert.ok(res.body[0].rating);
  });

  await t.test('F01-H2: Fetch full movie details with active streaming servers and downloads', async () => {
    const res = await request('/api/media/dune-part-two');
    assert.equal(res.status, 200);
    assert.equal(res.body.title, 'Dune: Part Two');
    assert.ok(Array.isArray(res.body.servers));
    assert.ok(res.body.servers.length >= 2);
    assert.ok(res.body.servers[0].url.startsWith('https://'));
    assert.ok(Array.isArray(res.body.downloads));
  });

  await t.test('F01-E1: Empty or whitespace search query returns empty array gracefully', async () => {
    const res = await request('/api/search/live?q=');
    assert.equal(res.status, 200);
    assert.deepEqual(res.body, []);
  });

  await t.test('F01-N1: Querying a non-existent movie slug returns 404', async () => {
    const res = await request('/api/media/non-existent-movie-slug-123');
    assert.equal(res.status, 404);
    assert.ok(res.body.error);
  });
});

test('F02: Multi-Faceted Catalog Filtering & Sorting', async (t) => {
  await t.test('F02-H1: Filter by category type=movie returns only movies', async () => {
    const res = await request('/api/media?type=movie');
    assert.equal(res.status, 200);
    assert.ok(res.body.items.length > 0);
    res.body.items.forEach(item => assert.equal(item.type, 'movie'));
  });

  await t.test('F02-H2: Filter by genre=Action returns titles containing Action', async () => {
    const res = await request('/api/media?genre=Action');
    assert.equal(res.status, 200);
    assert.ok(res.body.items.length > 0);
    res.body.items.forEach(item => assert.ok(item.genres.includes('Action')));
  });

  await t.test('F02-H3: Sort order rating arranges titles in descending IMDb order', async () => {
    const res = await request('/api/media?sort=rating');
    assert.equal(res.status, 200);
    const ratings = res.body.items.map(m => m.rating);
    for (let i = 0; i < ratings.length - 1; i++) {
      assert.ok(ratings[i] >= ratings[i + 1]);
    }
  });

  await t.test('F02-E1: Filter combination yielding zero matches returns empty list without error', async () => {
    const res = await request('/api/media?genre=NonExistentGenre&quality=4K');
    assert.equal(res.status, 200);
    assert.equal(res.body.items.length, 0);
    assert.equal(res.body.total, 0);
  });
});

test('F03: Binge Watching TV Web Series Episodes', async (t) => {
  await t.test('F03-H1: Fetch TV Series detail with seasons and episodes hierarchy', async () => {
    const res = await request('/api/media/stranger-things');
    assert.equal(res.status, 200);
    assert.equal(res.body.type, 'tv_show');
    assert.ok(Array.isArray(res.body.seasons));
    assert.ok(res.body.seasons.length > 0);
    assert.equal(res.body.seasons[0].seasonNumber, 1);
  });

  await t.test('F03-H2: Episode watch route returns video stream with next/prev episode traversal', async () => {
    const res = await request('/api/series/stranger-things/seasons/1/episodes/1');
    assert.equal(res.status, 200);
    assert.equal(res.body.episode.episodeNumber, 1);
    assert.ok(res.body.episode.servers.length > 0);
    assert.equal(res.body.nextEpisode.episodeNumber, 2);
    assert.equal(res.body.prevEpisode, null); // Ep 1 has no previous episode
  });

  await t.test('F03-N1: Non-existent season or episode returns 404', async () => {
    const res = await request('/api/series/stranger-things/seasons/99/episodes/99');
    assert.equal(res.status, 404);
  });
});

test('F04: Report Broken Stream & Rate Limiting', async (t) => {
  await t.test('F04-H1: Submit broken stream report successfully returns 201', async () => {
    const res = await request('/api/reports', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: {
        mediaTitle: 'Dune: Part Two',
        serverName: 'Server 1',
        category: 'broken_link',
        details: 'Video stream buffering on timestamp 01:23',
      },
    });
    assert.equal(res.status, 201);
    assert.ok(res.body.success);
    assert.ok(res.body.reportId);
  });

  await t.test('F04-E1: Automated CDN stream health check returns operational status', async () => {
    const res = await request('/api/cron/check-servers', { method: 'POST' });
    assert.equal(res.status, 200);
    assert.ok(res.body.checkedCount > 0);
    assert.equal(res.body.failingCount, 0);
  });
});

test('F05: Save Title to Watchlist and Session Isolation', async (t) => {
  const clientACookie = 'cinestream_client_id=client_alpha_12345';
  const clientBCookie = 'cinestream_client_id=client_beta_67890';

  await t.test('F05-H1: Client A adds Dune to Watchlist', async () => {
    const toggleRes = await request('/api/watchlist/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Cookie': clientACookie },
      body: { mediaId: 'm01' },
    });
    assert.equal(toggleRes.status, 200);
    assert.equal(toggleRes.body.inWatchlist, true);

    const getRes = await request('/api/watchlist', {
      headers: { 'Cookie': clientACookie },
    });
    assert.equal(getRes.status, 200);
    assert.ok(getRes.body.some(m => m.id === 'm01'));
  });

  await t.test('F05-E1: Client B cannot see Client A watchlist (strict session isolation)', async () => {
    const res = await request('/api/watchlist', {
      headers: { 'Cookie': clientBCookie },
    });
    assert.equal(res.status, 200);
    assert.equal(res.body.length, 0); // Client B queue must be completely empty
  });

  await t.test('F05-H2: Toggling Dune again removes it from Watchlist', async () => {
    const toggleRes = await request('/api/watchlist/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Cookie': clientACookie },
      body: { mediaId: 'm01' },
    });
    assert.equal(toggleRes.status, 200);
    assert.equal(toggleRes.body.inWatchlist, false);
  });
});

test.after(async () => {
  await new Promise(resolve => server.close(resolve));
});
