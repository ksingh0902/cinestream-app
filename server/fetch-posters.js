const https = require('https');

const titles = [
  { name: 'Panchayat', path: '/tv/100440-panchayat' },
  { name: 'Mirzapur', path: '/tv/82596-mirzapur' },
  { name: 'The Family Man', path: '/tv/86831-the-family-man' },
  { name: 'Kota Factory', path: '/tv/88565-kota-factory' },
  { name: 'Dunki', path: '/movie/960876-dunki' },
  { name: 'Shaitaan', path: '/movie/1226578-shaitaan' },
  { name: 'Chandu Champion', path: '/movie/1149488-chandu-champion' },
  { name: 'Munjya', path: '/movie/1195632-munjya' },
  { name: 'Pushpa 2', path: '/movie/872585-pushpa-2-the-rule' },
  { name: 'Maharaja', path: '/movie/1114513-maharaja' },
  { name: '12th Fail', path: '/movie/1181548-12th-fail' }
];

function fetchWithRedirect(url, cb) {
  https.get(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
  }, res => {
    if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
      let loc = res.headers.location;
      if (!loc.startsWith('http')) loc = 'https://www.themoviedb.org' + loc;
      return fetchWithRedirect(loc, cb);
    }
    let html = '';
    res.on('data', c => html += c);
    res.on('end', () => cb(html, res.statusCode));
  });
}

titles.forEach(item => {
  fetchWithRedirect('https://www.themoviedb.org' + item.path, (html, code) => {
    const m = html.match(/https:\/\/image\.tmdb\.org\/t\/p\/[^\/]+\/([a-zA-Z0-9_-]+\.jpg)/);
    if (m) {
      console.log(`${item.name} | https://image.tmdb.org/t/p/w500/${m[1]}`);
    } else {
      console.log(`${item.name} | not found (${code})`);
    }
  });
});
