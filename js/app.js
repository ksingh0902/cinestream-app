/**
 * CineStream Application Engine
 * Handles SPA client-side routing, search autocomplete, multi-server video player,
 * watchlist persistence, interactive filters, theater mode, and toast notifications.
 */

class CineStreamApp {
  constructor() {
    this.currentRoute = '';
    this.params = {};
    this.watchlist = this.loadWatchlist();
    this.activeServerIndex = 0;
    this.theaterMode = false;
    this.activeFilters = {
      type: 'all',
      genre: 'all',
      year: 'all',
      quality: 'all',
      language: 'all',
      sort: 'trending'
    };

    this.init();
  }

  init() {
    this.bindEvents();
    this.updateWatchlistBadge();
    this.handleRoute();
  }

  // =========================================================================
  // Watchlist Management (LocalStorage)
  // =========================================================================
  loadWatchlist() {
    try {
      const saved = localStorage.getItem('cinestream_watchlist');
      return saved ? JSON.parse(saved) : [];
    } catch (e) {
      return [];
    }
  }

  saveWatchlist() {
    try {
      localStorage.setItem('cinestream_watchlist', JSON.stringify(this.watchlist));
      this.updateWatchlistBadge();
    } catch (e) {
      console.error('Error saving watchlist', e);
    }
  }

  toggleWatchlist(mediaId) {
    const item = CATALOG_DATA.find(m => m.id === mediaId);
    if (!item) return;

    const index = this.watchlist.findIndex(id => id === mediaId);
    if (index > -1) {
      this.watchlist.splice(index, 1);
      this.showToast(`Removed "${item.title}" from your Watchlist`, 'info');
    } else {
      this.watchlist.push(mediaId);
      this.showToast(`Saved "${item.title}" to your Watchlist!`, 'success');
    }
    this.saveWatchlist();

    // Re-render if on watchlist page
    if (this.currentRoute === 'watchlist') {
      this.renderWatchlistPage();
    } else {
      // Update bookmark buttons currently on screen
      document.querySelectorAll(`[data-bookmark-id="${mediaId}"]`).forEach(btn => {
        btn.classList.toggle('active', this.isInWatchlist(mediaId));
      });
    }
  }

  isInWatchlist(mediaId) {
    return this.watchlist.includes(mediaId);
  }

  updateWatchlistBadge() {
    const badge = document.getElementById('watchlist-count');
    if (badge) {
      badge.textContent = this.watchlist.length;
    }
  }

  // =========================================================================
  // Routing Engine
  // =========================================================================
  bindEvents() {
    window.addEventListener('hashchange', () => this.handleRoute());

    // Search events
    const searchInput = document.getElementById('global-search-input');
    const searchDropdown = document.getElementById('search-dropdown');

    if (searchInput) {
      let debounceTimer = null;
      searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        const query = e.target.value.trim();
        if (query.length < 2) {
          searchDropdown.classList.remove('active');
          return;
        }
        debounceTimer = setTimeout(() => {
          this.handleLiveSearch(query);
        }, 120);
      });

      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          const query = searchInput.value.trim();
          if (query) {
            searchDropdown.classList.remove('active');
            window.location.hash = `#/search?q=${encodeURIComponent(query)}`;
          }
        } else if (e.key === 'Escape') {
          searchDropdown.classList.remove('active');
        }
      });
    }

    // Close search dropdown on click outside
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.search-wrapper')) {
        const dd = document.getElementById('search-dropdown');
        if (dd) dd.classList.remove('active');
      }
    });

    // Close modal on backdrop click or ESC
    const modalRoot = document.getElementById('modal-root');
    if (modalRoot) {
      modalRoot.addEventListener('click', (e) => {
        if (e.target === modalRoot) this.closeModal();
      });
    }
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.closeModal();
        if (this.theaterMode) this.toggleTheaterMode(false);
      }
    });
  }

  handleRoute() {
    const hash = window.location.hash.slice(1) || '/';
    const [path, queryString] = hash.split('?');
    const segments = path.split('/').filter(Boolean);

    // Update nav active link
    const rootRoute = segments[0] || 'home';
    document.querySelectorAll('.nav-item a').forEach(a => {
      a.classList.toggle('active', a.getAttribute('data-route') === rootRoute);
    });

    // Ensure theater mode resets when navigating away
    if (this.theaterMode && !path.startsWith('/movie') && !path.startsWith('/watch')) {
      this.toggleTheaterMode(false);
    }

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Route matching
    if (segments.length === 0 || segments[0] === 'home') {
      this.currentRoute = 'home';
      this.renderHomePage();
    } else if (segments[0] === 'movies') {
      this.currentRoute = 'movies';
      this.activeFilters.type = 'movie';
      this.renderCatalogPage('All Movies');
    } else if (segments[0] === 'series') {
      this.currentRoute = 'series';
      this.activeFilters.type = 'tv_show';
      this.renderCatalogPage('Web Series & TV Shows');
    } else if (segments[0] === 'trending') {
      this.currentRoute = 'trending';
      this.activeFilters.sort = 'trending';
      this.renderCatalogPage('Trending Now');
    } else if (segments[0] === 'genres') {
      this.currentRoute = 'genres';
      this.renderGenresPage();
    } else if (segments[0] === 'dmca') {
      this.currentRoute = 'dmca';
      this.renderDmcaPage();
    } else if (segments[0] === 'watchlist') {
      this.currentRoute = 'watchlist';
      this.renderWatchlistPage();
    } else if (segments[0] === 'search') {
      this.currentRoute = 'search';
      const params = new URLSearchParams(queryString || '');
      this.renderSearchResultsPage(params.get('q') || '');
    } else if (segments[0] === 'movie' && segments[1]) {
      this.currentRoute = 'movie-detail';
      this.renderMovieDetailPage(segments[1]);
    } else if (segments[0] === 'series' && segments[1]) {
      this.currentRoute = 'series-detail';
      this.renderSeriesDetailPage(segments[1]);
    } else if (segments[0] === 'watch' && segments[1] && segments[2] && segments[3]) {
      this.currentRoute = 'episode-watch';
      this.renderEpisodeWatchPage(segments[1], parseInt(segments[2]), parseInt(segments[3]));
    } else {
      this.renderNotFoundPage();
    }
  }

  // =========================================================================
  // Live Search Autocomplete (S04)
  // =========================================================================
  handleLiveSearch(query) {
    const q = query.toLowerCase();
    const matches = CATALOG_DATA.filter(item => {
      return item.title.toLowerCase().includes(q) ||
             item.genres.some(g => g.toLowerCase().includes(q)) ||
             item.cast.some(c => c.toLowerCase().includes(q));
    }).slice(0, 6);

    const dropdown = document.getElementById('search-dropdown');
    if (!dropdown) return;

    if (matches.length === 0) {
      dropdown.innerHTML = `
        <div style="padding: var(--space-4); text-align: center; color: var(--color-text-muted); font-size: var(--type-sm-size);">
          No matches found for "${query}"
        </div>
      `;
    } else {
      dropdown.innerHTML = matches.map(m => `
        <div class="search-dropdown-item" onclick="window.location.hash='#/${m.type === 'movie' ? 'movie' : 'series'}/${m.slug}'; document.getElementById('search-dropdown').classList.remove('active');">
          <img src="${m.poster}" alt="${m.title}" class="search-item-thumb">
          <div class="search-item-details">
            <div class="search-item-title">${m.title}</div>
            <div class="search-item-meta">
              <span class="badge badge-4k">${m.quality}</span>
              <span>${m.year}</span>
              <span>•</span>
              <span style="color: var(--color-warning);">★ ${m.rating}</span>
              <span>•</span>
              <span style="text-transform: capitalize;">${m.type === 'movie' ? 'Movie' : 'Series'}</span>
            </div>
          </div>
        </div>
      `).join('');
    }
    dropdown.classList.add('active');
  }

  // =========================================================================
  // S01: Homepage / Discover
  // =========================================================================
  renderHomePage() {
    const featured = CATALOG_DATA.find(m => m.featured) || CATALOG_DATA[0];
    const trending = CATALOG_DATA.filter(m => m.trending);
    const bollywood = CATALOG_DATA.filter(m => m.language === 'Hindi');
    const hollywood = CATALOG_DATA.filter(m => m.language === 'Dual Audio');
    const series = CATALOG_DATA.filter(m => m.type === 'tv_show');

    const appRoot = document.getElementById('app-root');
    appRoot.innerHTML = `
      <!-- Hero Featured Slider Banner -->
      <section class="hero-banner">
        <img src="${featured.backdrop}" alt="${featured.title}" class="hero-backdrop-img">
        <div class="hero-gradient-overlay"></div>
        <div class="hero-content">
          <div class="hero-tags">
            <span class="badge badge-4k">${featured.quality}</span>
            <span class="badge badge-dub">${featured.language}</span>
            <span class="badge badge-rating">★ ${featured.rating} IMDb</span>
            <span style="color: var(--color-text-muted); font-size: var(--type-xs-size); font-weight: 500;">${featured.year} • ${featured.runtime} min</span>
          </div>
          <h1 class="hero-title">${featured.title}</h1>
          <p class="hero-synopsis">${featured.synopsis}</p>
          <div class="hero-actions">
            <a href="#/${featured.type === 'movie' ? 'movie' : 'series'}/${featured.slug}" class="btn btn-primary btn-lg">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
              Watch Now
            </a>
            <button class="btn btn-secondary btn-lg" onclick="app.openTrailerModal('${featured.trailer}', '${featured.title}')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <polygon points="10 8 16 12 10 16 10 8"></polygon>
              </svg>
              Official Trailer
            </button>
            <button class="icon-btn ${this.isInWatchlist(featured.id) ? 'active' : ''}" data-bookmark-id="${featured.id}" onclick="app.toggleWatchlist('${featured.id}')" aria-label="Add to Watchlist">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="${this.isInWatchlist(featured.id) ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
                <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
              </svg>
            </button>
          </div>
        </div>
      </section>

      <!-- Trending Section -->
      <section style="margin-bottom: var(--space-10);">
        <div class="section-header">
          <h2 class="section-title">Trending This Week</h2>
          <a href="#/trending" class="btn btn-ghost btn-sm">View All &rarr;</a>
        </div>
        <div class="media-grid">
          ${trending.map(m => this.renderMediaCard(m)).join('')}
        </div>
      </section>

      <!-- Bollywood & Hindi Movies -->
      <section style="margin-bottom: var(--space-10);">
        <div class="section-header">
          <h2 class="section-title">Latest Bollywood Movies</h2>
          <a href="#/movies" class="btn btn-ghost btn-sm">Browse Catalog &rarr;</a>
        </div>
        <div class="media-grid">
          ${bollywood.map(m => this.renderMediaCard(m)).join('')}
        </div>
      </section>

      <!-- Hollywood Dual Audio Section -->
      <section style="margin-bottom: var(--space-10);">
        <div class="section-header">
          <h2 class="section-title">Hollywood Dual Audio Releases</h2>
          <a href="#/movies" class="btn btn-ghost btn-sm">Browse Catalog &rarr;</a>
        </div>
        <div class="media-grid">
          ${hollywood.map(m => this.renderMediaCard(m)).join('')}
        </div>
      </section>

      <!-- Top Web Series Section -->
      <section style="margin-bottom: var(--space-10);">
        <div class="section-header">
          <h2 class="section-title">Binge-Worthy TV Series</h2>
          <a href="#/series" class="btn btn-ghost btn-sm">View All Series &rarr;</a>
        </div>
        <div class="media-grid">
          ${series.map(m => this.renderMediaCard(m)).join('')}
        </div>
      </section>
    `;
  }

  // =========================================================================
  // Media Card Component Template
  // =========================================================================
  renderMediaCard(item) {
    const isBookmarked = this.isInWatchlist(item.id);
    return `
      <div class="media-card" onclick="window.location.hash='#/${item.type === 'movie' ? 'movie' : 'series'}/${item.slug}'">
        <div class="poster-box">
          <img src="${item.poster}" alt="${item.title}" class="poster-img" loading="lazy">
          <div class="card-top-badges">
            <span class="badge badge-4k">${item.quality}</span>
            <span class="badge badge-rating">★ ${item.rating}</span>
          </div>
          <div class="card-hover-overlay">
            <div class="card-play-btn" aria-label="Play">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
            </div>
            <button class="card-bookmark-btn ${isBookmarked ? 'active' : ''}" data-bookmark-id="${item.id}" onclick="event.stopPropagation(); app.toggleWatchlist('${item.id}');" aria-label="Add to Watchlist">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="${isBookmarked ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
                <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
              </svg>
            </button>
          </div>
        </div>
        <div class="card-details">
          <div class="card-title" title="${item.title}">${item.title}</div>
          <div class="card-subtitle">
            <span>${item.year}</span>
            <span>${item.language}</span>
          </div>
        </div>
      </div>
    `;
  }

  // =========================================================================
  // S02 & S03: Movies & TV Shows Catalog with Multi-Facet Filters
  // =========================================================================
  renderCatalogPage(pageHeading) {
    const filtered = this.getFilteredCatalog();

    const appRoot = document.getElementById('app-root');
    appRoot.innerHTML = `
      <div style="margin-top: var(--space-6);">
        <h1 style="font-family: var(--font-display); font-size: var(--type-2xl-size); font-weight: 800; margin-bottom: var(--space-4);">${pageHeading}</h1>

        <!-- Filter Bar (S02) -->
        <div class="filter-bar">
          <div class="filter-pills">
            <button class="filter-pill ${this.activeFilters.type === 'all' ? 'active' : ''}" onclick="app.setFilter('type', 'all')">All Titles</button>
            <button class="filter-pill ${this.activeFilters.type === 'movie' ? 'active' : ''}" onclick="app.setFilter('type', 'movie')">Movies</button>
            <button class="filter-pill ${this.activeFilters.type === 'tv_show' ? 'active' : ''}" onclick="app.setFilter('type', 'tv_show')">Web Series</button>
          </div>

          <div class="filter-selects">
            <select class="filter-select" onchange="app.setFilter('genre', this.value)">
              <option value="all">All Genres</option>
              ${TAXONOMY.genres.map(g => `<option value="${g}" ${this.activeFilters.genre === g ? 'selected' : ''}>${g}</option>`).join('')}
            </select>

            <select class="filter-select" onchange="app.setFilter('language', this.value)">
              <option value="all">All Languages</option>
              ${TAXONOMY.languages.map(l => `<option value="${l}" ${this.activeFilters.language === l ? 'selected' : ''}>${l}</option>`).join('')}
            </select>

            <select class="filter-select" onchange="app.setFilter('quality', this.value)">
              <option value="all">Quality</option>
              ${TAXONOMY.qualities.map(q => `<option value="${q}" ${this.activeFilters.quality === q ? 'selected' : ''}>${q}</option>`).join('')}
            </select>

            <select class="filter-select" onchange="app.setFilter('sort', this.value)">
              <option value="trending" ${this.activeFilters.sort === 'trending' ? 'selected' : ''}>Most Popular</option>
              <option value="rating" ${this.activeFilters.sort === 'rating' ? 'selected' : ''}>Top Rated</option>
              <option value="latest" ${this.activeFilters.sort === 'latest' ? 'selected' : ''}>Latest Release</option>
            </select>
          </div>
        </div>

        <!-- Catalog Grid -->
        ${filtered.length === 0 ? `
          <div style="text-align: center; padding: var(--space-16) 0; color: var(--color-text-muted);">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin: 0 auto var(--space-3);">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <h3 style="color: var(--color-text); font-size: var(--type-lg-size); margin-bottom: var(--space-2);">No matching titles found</h3>
            <p>Try adjusting your filters or clearing search criteria.</p>
            <button class="btn btn-secondary btn-md" style="margin-top: var(--space-4);" onclick="app.resetFilters()">Reset All Filters</button>
          </div>
        ` : `
          <div class="media-grid">
            ${filtered.map(m => this.renderMediaCard(m)).join('')}
          </div>
        `}
      </div>
    `;
  }

  setFilter(key, value) {
    this.activeFilters[key] = value;
    this.renderCatalogPage(this.currentRoute === 'series' ? 'Web Series & TV Shows' : 'All Movies');
  }

  resetFilters() {
    this.activeFilters = {
      type: 'all',
      genre: 'all',
      year: 'all',
      quality: 'all',
      language: 'all',
      sort: 'trending'
    };
    this.renderCatalogPage('All Titles');
  }

  getFilteredCatalog() {
    return CATALOG_DATA.filter(item => {
      if (this.activeFilters.type !== 'all' && item.type !== this.activeFilters.type) return false;
      if (this.activeFilters.genre !== 'all' && !item.genres.includes(this.activeFilters.genre)) return false;
      if (this.activeFilters.language !== 'all' && item.language !== this.activeFilters.language) return false;
      if (this.activeFilters.quality !== 'all' && item.quality !== this.activeFilters.quality) return false;
      return true;
    }).sort((a, b) => {
      if (this.activeFilters.sort === 'rating') return b.rating - a.rating;
      if (this.activeFilters.sort === 'latest') return b.year - a.year;
      return b.views - a.views;
    });
  }

  // =========================================================================
  // S05: Movie Detail & Multi-Server Watch Page
  // =========================================================================
  renderMovieDetailPage(slug) {
    const movie = CATALOG_DATA.find(m => m.slug === slug);
    if (!movie) {
      this.renderNotFoundPage();
      return;
    }

    this.activeServerIndex = 0;
    const allServers = [...movie.servers];
    if (movie.trailer && !allServers.some(s => s.url === movie.trailer)) {
      allServers.push({
        id: "s-trailer",
        name: "Official HD Trailer",
        type: "embed",
        url: movie.trailer
      });
    }
    const activeServer = allServers[0] || { name: 'Server 1', url: 'https://vjs.zencdn.net/v/oceans.mp4' };
    const related = CATALOG_DATA.filter(m => m.id !== movie.id && m.genres.some(g => movie.genres.includes(g))).slice(0, 6);

    const appRoot = document.getElementById('app-root');
    appRoot.innerHTML = `
      <div class="watch-page">
        <!-- Header controls (Theater mode toggle, Broken link report) -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4);">
          <div style="display: flex; align-items: center; gap: var(--space-2);">
            <a href="#/movies" class="btn btn-ghost btn-sm">&larr; Back to Catalog</a>
            <span style="color: var(--color-border);">|</span>
            <span style="color: var(--color-text-muted); font-size: var(--type-sm-size); font-weight: 500;">Now Streaming: <strong>${movie.title}</strong></span>
          </div>

          <div style="display: flex; align-items: center; gap: var(--space-2);">
            <button class="theater-mode-trigger ${this.theaterMode ? 'active' : ''}" onclick="app.toggleTheaterMode()">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="5"></circle>
                <line x1="12" y1="1" x2="12" y2="3"></line>
                <line x1="12" y1="21" x2="12" y2="23"></line>
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                <line x1="1" y1="12" x2="3" y2="12"></line>
                <line x1="21" y1="12" x2="23" y2="12"></line>
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
              </svg>
              <span>${this.theaterMode ? 'Lights On' : 'Lights Off'}</span>
            </button>

            <button class="btn btn-danger btn-sm" onclick="app.openReportModal('${movie.title}', '${activeServer.name}')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
              </svg>
              Report Broken Link
            </button>
          </div>
        </div>

        <!-- Video Player Box (S05) -->
        <div class="player-wrapper" id="player-wrapper">
          ${this.getPlayerMarkup(activeServer, movie.backdrop || movie.poster)}
        </div>

        <!-- Server Selector Bar -->
        <div class="server-panel">
          <div style="display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap;">
            <span style="font-size: var(--type-xs-size); font-weight: 700; color: var(--color-text-muted); text-transform: uppercase;">Streaming Servers:</span>
            <div class="server-list">
              ${allServers.map((s, idx) => `
                <button class="server-button ${idx === 0 ? 'active' : ''}" data-server-idx="${idx}" onclick="app.switchServer(${idx}, '${s.url}', '${s.name}', '${s.type || 'video'}')">
                  <span class="status-dot"></span>
                  ${s.name}
                </button>
              `).join('')}
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap;">
            <a href="${activeServer.url}" target="_blank" rel="noopener noreferrer" class="btn btn-ghost btn-sm" id="external-mirror-btn" style="font-size: var(--type-xs-size); color: var(--color-primary);">
              Open Mirror in Clean Tab ↗
            </a>
            <div style="font-size: var(--type-xs-size); color: var(--color-success); display: flex; align-items: center; gap: 4px;">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"></polyline></svg>
              Ad-Free Sandbox Active
            </div>
          </div>
        </div>

        <!-- Detail Layout (Metadata, Cast, Downloads, Recommendations) -->
        <div class="watch-layout">
          <div class="watch-details-section">
            <div class="watch-info-header">
              <img src="${movie.poster}" alt="${movie.title}" class="watch-poster-thumb">
              <div class="watch-title-block">
                <h1>${movie.title}</h1>
                <div class="watch-meta-chips">
                  <span class="badge badge-4k">${movie.quality}</span>
                  <span class="badge badge-dub">${movie.language}</span>
                  <span class="badge badge-rating">★ ${movie.rating} IMDb</span>
                  <span style="color: var(--color-text-muted); font-size: var(--type-sm-size);">${movie.year} • ${movie.runtime} min</span>
                </div>
                <div style="display: flex; gap: var(--space-2); margin-top: var(--space-3);">
                  <button class="btn btn-secondary btn-sm" onclick="app.toggleWatchlist('${movie.id}')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="${this.isInWatchlist(movie.id) ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
                      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
                    </svg>
                    <span>${this.isInWatchlist(movie.id) ? 'Saved in Watchlist' : 'Add to Watchlist'}</span>
                  </button>
                  <button class="btn btn-ghost btn-sm" onclick="app.openTrailerModal('${movie.trailer}', '${movie.title}')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>
                    Trailer
                  </button>
                </div>
              </div>
            </div>

            <h3 style="font-size: var(--type-md-size); margin-bottom: var(--space-2);">Storyline</h3>
            <p class="watch-synopsis">${movie.synopsis}</p>

            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-3); background: var(--color-surface); padding: var(--space-4); border-radius: var(--radius-md); border: 1px solid var(--color-border); margin-bottom: var(--space-6);">
              <div>
                <span style="color: var(--color-text-muted); font-size: var(--type-xs-size); display: block;">Director</span>
                <span style="font-weight: 600; font-size: var(--type-sm-size);">${movie.director}</span>
              </div>
              <div>
                <span style="color: var(--color-text-muted); font-size: var(--type-xs-size); display: block;">Genres</span>
                <span style="font-weight: 600; font-size: var(--type-sm-size);">${movie.genres.join(', ')}</span>
              </div>
              <div style="grid-column: span 2;">
                <span style="color: var(--color-text-muted); font-size: var(--type-xs-size); display: block;">Starring Cast</span>
                <span style="font-weight: 500; font-size: var(--type-sm-size); color: var(--color-text);">${movie.cast.join(', ')}</span>
              </div>
            </div>

            <!-- Download Links Table -->
            <div class="download-section">
              <h3 style="font-size: var(--type-md-size); font-weight: 700; margin-bottom: var(--space-2); display: flex; align-items: center; gap: var(--space-2);">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="7 10 12 15 17 10"></polyline>
                  <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                Fast Download Links
              </h3>
              <p style="color: var(--color-text-muted); font-size: var(--type-xs-size); margin-bottom: var(--space-3);">High-speed direct cloud mirrors for offline viewing.</p>
              <table class="download-table">
                <thead>
                  <tr>
                    <th>Quality</th>
                    <th>File Size</th>
                    <th>Host Provider</th>
                    <th>Download Link</th>
                  </tr>
                </thead>
                <tbody>
                  ${(movie.downloads || []).map(dl => `
                    <tr>
                      <td><span class="badge badge-4k">${dl.quality}</span></td>
                      <td>${dl.size}</td>
                      <td>${dl.host}</td>
                      <td>
                        <a href="${activeServer.url}" download="${movie.slug}.mp4" class="btn btn-secondary btn-sm" onclick="app.showToast('Download started for ${dl.quality}', 'info')">
                          Download
                        </a>
                      </td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          </div>

          <!-- Watch Sidebar (Related Movies) -->
          <div class="watch-sidebar">
            <h3 style="font-size: var(--type-md-size); font-weight: 700; margin-bottom: var(--space-4);">You May Also Like</h3>
            <div style="display: flex; flex-direction: column; gap: var(--space-3);">
              ${related.map(r => `
                <div style="display: flex; gap: var(--space-3); background: var(--color-surface); padding: var(--space-2); border-radius: var(--radius-md); border: 1px solid var(--color-border); cursor: pointer;" onclick="window.location.hash='#/movie/${r.slug}'">
                  <img src="${r.poster}" alt="${r.title}" style="width: 50px; height: 75px; object-fit: cover; border-radius: var(--radius-xs);">
                  <div style="flex: 1; min-width: 0;">
                    <div style="font-size: var(--type-sm-size); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${r.title}</div>
                    <div style="font-size: var(--type-xs-size); color: var(--color-text-muted); margin-top: 2px;">${r.year} • ★ ${r.rating}</div>
                    <span class="badge badge-4k" style="margin-top: 4px;">${r.quality}</span>
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        </div>
      </div>
    `;

    this.initPlayerControls();
  }

  getPlayerMarkup(server, poster) {
    if (!server) server = { type: 'video', url: 'https://vjs.zencdn.net/v/oceans.mp4' };
    const isEmbed = server.type === 'embed' || (server.url && (server.url.includes('vidlink') || server.url.includes('2embed') || server.url.includes('vidsrc') || server.url.includes('youtube.com')));

    if (isEmbed) {
      return `
        <iframe id="main-video-player" class="player-video-element" src="${server.url}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen referrerpolicy="origin" style="background-color: #000;"></iframe>
      `;
    }

    return `
      <video id="main-video-player" class="player-video-element" controls playsinline preload="auto" poster="${poster || ''}">
        <source src="${server.url}" type="video/mp4">
        Your browser does not support HTML5 video streaming.
      </video>
      <div class="player-play-overlay" id="player-play-overlay" title="Click to Start Streaming">
        <button class="player-big-play-btn" aria-label="Start Stream">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
            <polygon points="5 3 19 12 5 21 5 3"></polygon>
          </svg>
        </button>
        <div class="player-play-label">Click to Start Stream • Multi-Server VIP</div>
      </div>
    `;
  }

  switchServer(serverIdx, url, serverName, serverType) {
    this.activeServerIndex = serverIdx;
    document.querySelectorAll('.server-button').forEach(btn => {
      btn.classList.toggle('active', parseInt(btn.getAttribute('data-server-idx')) === serverIdx);
    });

    const wrapper = document.getElementById('player-wrapper');
    if (!wrapper) return;

    wrapper.innerHTML = this.getPlayerMarkup({ type: serverType, url }, '');
    const extBtn = document.getElementById('external-mirror-btn');
    if (extBtn) extBtn.href = url;

    if (serverType !== 'embed' && !url.includes('vidlink') && !url.includes('2embed') && !url.includes('vidsrc') && !url.includes('youtube.com')) {
      this.initPlayerControls();
    }
    this.showToast(`Switched playback to ${serverName}`, 'info');
  }

  initPlayerControls() {
    const video = document.getElementById('main-video-player');
    const overlay = document.getElementById('player-play-overlay');
    if (!video || video.tagName.toLowerCase() !== 'video') return;

    const startPlaying = () => {
      const playPromise = video.play();
      if (playPromise !== undefined) {
        playPromise.then(() => {
          if (overlay) overlay.style.display = 'none';
        }).catch(err => {
          console.warn('Autoplay unmuted blocked by browser policy. Retrying muted:', err);
          video.muted = true;
          video.play().then(() => {
            if (overlay) overlay.style.display = 'none';
            this.showToast('Playing muted per browser policy (click speaker icon on player to unmute)', 'info');
          }).catch(e => {
            console.error('Play requires direct gesture:', e);
            if (overlay) overlay.style.display = 'flex';
          });
        });
      }
    };

    if (overlay) {
      overlay.addEventListener('click', (e) => {
        e.stopPropagation();
        video.muted = false;
        startPlaying();
      });
    }

    video.addEventListener('play', () => {
      if (overlay) overlay.style.display = 'none';
    });

    video.addEventListener('pause', () => {
      if (overlay && (video.ended || video.currentTime === 0)) {
        overlay.style.display = 'flex';
      }
    });

    video.addEventListener('error', (e) => {
      console.warn('Video element error:', e);
      this.showToast('Current mirror buffering, auto-switching server...', 'warning');
      const buttons = Array.from(document.querySelectorAll('.server-button'));
      const activeIdx = buttons.findIndex(b => b.classList.contains('active'));
      const nextBtn = buttons[(activeIdx + 1) % buttons.length];
      if (nextBtn && buttons.length > 1) {
        setTimeout(() => nextBtn.click(), 800);
      }
    });

    // Attempt start
    startPlaying();
  }

  toggleTheaterMode(explicitState) {
    this.theaterMode = explicitState !== undefined ? explicitState : !this.theaterMode;
    document.body.classList.toggle('theater-mode', this.theaterMode);

    const trigger = document.querySelector('.theater-mode-trigger');
    if (trigger) {
      trigger.classList.toggle('active', this.theaterMode);
      trigger.querySelector('span').textContent = this.theaterMode ? 'Lights On' : 'Lights Off';
    }
    if (this.theaterMode) {
      this.showToast('Theater Mode activated (Press ESC to exit)', 'info');
    }
  }

  // =========================================================================
  // S06: TV Series Detail & Seasons Hub
  // =========================================================================
  renderSeriesDetailPage(slug) {
    const series = CATALOG_DATA.find(m => m.slug === slug);
    if (!series) {
      this.renderNotFoundPage();
      return;
    }

    const season = series.seasons ? series.seasons[0] : null;

    const appRoot = document.getElementById('app-root');
    appRoot.innerHTML = `
      <div class="watch-page">
        <div style="margin-bottom: var(--space-4);">
          <a href="#/series" class="btn btn-ghost btn-sm">&larr; Back to Series</a>
        </div>

        <div class="watch-info-header" style="margin-bottom: var(--space-8);">
          <img src="${series.poster}" alt="${series.title}" class="watch-poster-thumb" style="width: 140px;">
          <div class="watch-title-block">
            <h1>${series.title}</h1>
            <div class="watch-meta-chips">
              <span class="badge badge-4k">${series.quality}</span>
              <span class="badge badge-dub">${series.language}</span>
              <span class="badge badge-rating">★ ${series.rating} IMDb</span>
              <span style="color: var(--color-text-muted); font-size: var(--type-sm-size);">${series.year} • ${series.seasons ? series.seasons.length : 1} Seasons</span>
            </div>
            <p class="watch-synopsis" style="max-width: 800px;">${series.synopsis}</p>
            <div style="display: flex; gap: var(--space-3); margin-top: var(--space-4);">
              <a href="#/watch/${series.slug}/1/1" class="btn btn-primary btn-md">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                Watch Season 1 Ep 1
              </a>
              <button class="btn btn-secondary btn-md" onclick="app.toggleWatchlist('${series.id}')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="${this.isInWatchlist(series.id) ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
                  <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
                </svg>
                <span>${this.isInWatchlist(series.id) ? 'Saved' : 'Add to Watchlist'}</span>
              </button>
              <button class="btn btn-ghost btn-md" onclick="app.openTrailerModal('${series.trailer}', '${series.title}')">
                Official Trailer
              </button>
            </div>
          </div>
        </div>

        <!-- Seasons & Episodes Picker -->
        ${series.seasons ? `
          <div class="season-selector">
            <h2 style="font-size: var(--type-xl-size); font-weight: 700; margin-bottom: var(--space-4);">Seasons & Episodes</h2>
            <div class="season-tabs">
              ${series.seasons.map((s, idx) => `
                <button class="season-tab-btn ${idx === 0 ? 'active' : ''}" onclick="app.showSeason(${idx}, '${series.slug}')">
                  ${s.title} (${s.episodes ? s.episodes.length : s.episodesCount} Episodes)
                </button>
              `).join('')}
            </div>

            <div class="episodes-grid" id="episodes-container">
              ${(season.episodes || []).map(ep => `
                <div class="episode-card" onclick="window.location.hash='#/watch/${series.slug}/${season.seasonNumber}/${ep.episodeNumber}'">
                  <img src="${ep.still}" alt="${ep.title}" class="episode-thumb">
                  <div class="episode-info">
                    <div style="font-size: var(--type-xs-size); color: var(--color-accent); font-weight: 600;">Episode ${ep.episodeNumber} • ${ep.runtime} min</div>
                    <div class="episode-title">${ep.title}</div>
                    <div style="font-size: var(--type-xs-size); color: var(--color-text-muted); margin-top: 2px;">${ep.overview}</div>
                  </div>
                  <div class="btn btn-primary btn-sm" style="flex-shrink: 0;">Play</div>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }

  showSeason(seasonIdx, slug) {
    const series = CATALOG_DATA.find(m => m.slug === slug);
    if (!series || !series.seasons) return;

    document.querySelectorAll('.season-tab-btn').forEach((btn, idx) => {
      btn.classList.toggle('active', idx === seasonIdx);
    });

    const season = series.seasons[seasonIdx];
    const container = document.getElementById('episodes-container');
    if (container && season) {
      container.innerHTML = (season.episodes || []).map(ep => `
        <div class="episode-card" onclick="window.location.hash='#/watch/${series.slug}/${season.seasonNumber}/${ep.episodeNumber}'">
          <img src="${ep.still}" alt="${ep.title}" class="episode-thumb">
          <div class="episode-info">
            <div style="font-size: var(--type-xs-size); color: var(--color-accent); font-weight: 600;">Episode ${ep.episodeNumber} • ${ep.runtime} min</div>
            <div class="episode-title">${ep.title}</div>
            <div style="font-size: var(--type-xs-size); color: var(--color-text-muted); margin-top: 2px;">${ep.overview}</div>
          </div>
          <div class="btn btn-primary btn-sm" style="flex-shrink: 0;">Play</div>
        </div>
      `).join('');
    }
  }

  // =========================================================================
  // S07: TV Episode Watch Page with Next/Previous Traversal
  // =========================================================================
  renderEpisodeWatchPage(slug, seasonNum, episodeNum) {
    const series = CATALOG_DATA.find(m => m.slug === slug);
    if (!series || !series.seasons) {
      this.renderNotFoundPage();
      return;
    }

    const season = series.seasons.find(s => s.seasonNumber === seasonNum);
    if (!season || !season.episodes) {
      this.renderNotFoundPage();
      return;
    }

    const episode = season.episodes.find(e => e.episodeNumber === episodeNum);
    if (!episode) {
      this.renderNotFoundPage();
      return;
    }

    const nextEp = season.episodes.find(e => e.episodeNumber === episodeNum + 1);
    const prevEp = season.episodes.find(e => e.episodeNumber === episodeNum - 1);
    const activeServer = episode.servers && episode.servers[0] ? episode.servers[0] : { name: 'Server 1', url: 'https://vjs.zencdn.net/v/oceans.mp4' };

    const appRoot = document.getElementById('app-root');
    appRoot.innerHTML = `
      <div class="watch-page">
        <!-- Top Nav & Breadcrumbs -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4);">
          <div style="display: flex; align-items: center; gap: var(--space-2);">
            <a href="#/series/${series.slug}" class="btn btn-ghost btn-sm">&larr; ${series.title} Overview</a>
            <span style="color: var(--color-border);">|</span>
            <span style="color: var(--color-text-muted); font-size: var(--type-sm-size);">Season ${seasonNum} • Episode ${episodeNum}</span>
          </div>

          <button class="btn btn-danger btn-sm" onclick="app.openReportModal('${series.title} S${seasonNum}E${episodeNum}', '${activeServer.name}')">
            Report Broken Link
          </button>
        </div>

        <!-- Video Player Box (S07) -->
        <div class="player-wrapper" id="player-wrapper">
          ${this.getPlayerMarkup(activeServer, episode.still)}
        </div>

        <!-- Server Selector Bar -->
        <div class="server-panel">
          <div style="display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap;">
            <span style="font-size: var(--type-xs-size); font-weight: 700; color: var(--color-text-muted); text-transform: uppercase;">Episode Streaming Servers:</span>
            <div class="server-list">
              ${(episode.servers || [activeServer]).map((s, idx) => `
                <button class="server-button ${idx === 0 ? 'active' : ''}" data-server-idx="${idx}" onclick="app.switchServer(${idx}, '${s.url}', '${s.name}', '${s.type || 'video'}')">
                  <span class="status-dot"></span>
                  ${s.name}
                </button>
              `).join('')}
            </div>
          </div>
          <div style="font-size: var(--type-xs-size); color: var(--color-success); display: flex; align-items: center; gap: 4px;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"></polyline></svg>
            Ad-Free Sandbox Active
          </div>
        </div>

        <!-- Episode Navigation Bar -->
        <div class="episode-nav-bar">
          <div>
            ${prevEp ? `
              <a href="#/watch/${series.slug}/${seasonNum}/${prevEp.episodeNumber}" class="btn btn-secondary btn-sm">
                &larr; Ep ${prevEp.episodeNumber}: ${prevEp.title}
              </a>
            ` : `<button class="btn btn-secondary btn-sm" disabled>&larr; First Episode</button>`}
          </div>

          <div style="font-weight: 600; font-size: var(--type-sm-size);">
            Episode ${episodeNum}: ${episode.title}
          </div>

          <div>
            ${nextEp ? `
              <a href="#/watch/${series.slug}/${seasonNum}/${nextEp.episodeNumber}" class="btn btn-primary btn-sm">
                Next: Ep ${nextEp.episodeNumber} &rarr;
              </a>
            ` : `<button class="btn btn-secondary btn-sm" disabled>Season Finale</button>`}
          </div>
        </div>

        <!-- Episode Synopsis -->
        <div style="background: var(--color-surface); padding: var(--space-5); border-radius: var(--radius-lg); border: 1px solid var(--color-border);">
          <h2 style="font-size: var(--type-lg-size); font-weight: 700; margin-bottom: var(--space-2);">${episode.title}</h2>
          <p style="color: var(--color-text-muted); font-size: var(--type-sm-size); line-height: 1.6;">${episode.overview}</p>
        </div>
      </div>
    `;

    this.initPlayerControls();
  }

  // =========================================================================
  // S09: Watchlist Page
  // =========================================================================
  renderWatchlistPage() {
    const savedItems = CATALOG_DATA.filter(m => this.watchlist.includes(m.id));

    const appRoot = document.getElementById('app-root');
    appRoot.innerHTML = `
      <div style="margin-top: var(--space-6); min-height: 60vh;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-6);">
          <div>
            <h1 style="font-family: var(--font-display); font-size: var(--type-2xl-size); font-weight: 800;">My Saved Watchlist</h1>
            <p style="color: var(--color-text-muted); font-size: var(--type-sm-size);">Your bookmarked movies and series ready to stream anytime.</p>
          </div>
          ${savedItems.length > 0 ? `
            <button class="btn btn-danger btn-sm" onclick="app.clearWatchlist()">Clear All</button>
          ` : ''}
        </div>

        ${savedItems.length === 0 ? `
          <div style="text-align: center; padding: var(--space-16) 0; color: var(--color-text-muted); background: var(--color-surface); border-radius: var(--radius-lg); border: 1px solid var(--color-border);">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin: 0 auto var(--space-3); color: var(--color-text-muted);">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
            </svg>
            <h3 style="color: var(--color-text); font-size: var(--type-lg-size); margin-bottom: var(--space-2);">Your Watchlist is empty</h3>
            <p>Save movies or TV shows while browsing to keep track of what you want to watch next.</p>
            <a href="#/movies" class="btn btn-primary btn-md" style="margin-top: var(--space-4);">Explore Trending Movies</a>
          </div>
        ` : `
          <div class="media-grid">
            ${savedItems.map(m => this.renderMediaCard(m)).join('')}
          </div>
        `}
      </div>
    `;
  }

  clearWatchlist() {
    this.watchlist = [];
    this.saveWatchlist();
    this.renderWatchlistPage();
    this.showToast('Watchlist cleared', 'info');
  }

  // =========================================================================
  // S10: Genres Index Page
  // =========================================================================
  renderGenresPage() {
    const appRoot = document.getElementById('app-root');
    appRoot.innerHTML = `
      <div style="margin-top: var(--space-6);">
        <h1 style="font-family: var(--font-display); font-size: var(--type-2xl-size); font-weight: 800; margin-bottom: var(--space-2);">Browse by Genre</h1>
        <p style="color: var(--color-text-muted); font-size: var(--type-sm-size); margin-bottom: var(--space-6);">Explore titles categorized across cinematic themes and styles.</p>

        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: var(--space-4);">
          ${TAXONOMY.genres.map(genre => {
            const count = CATALOG_DATA.filter(m => m.genres.includes(genre)).length;
            return `
              <div style="background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-5); cursor: pointer; transition: all var(--motion-fast);" 
                   onclick="app.setFilter('genre', '${genre}'); window.location.hash='#/movies';"
                   onmouseover="this.style.borderColor='var(--color-accent)'; this.style.transform='translateY(-2px)';"
                   onmouseout="this.style.borderColor='var(--color-border)'; this.style.transform='none';">
                <h3 style="font-size: var(--type-md-size); font-weight: 700; margin-bottom: var(--space-1);">${genre}</h3>
                <span style="font-size: var(--type-xs-size); color: var(--color-text-muted);">${count} Titles available</span>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  }

  // =========================================================================
  // S11: DMCA & Legal Policy Notice
  // =========================================================================
  renderDmcaPage() {
    const appRoot = document.getElementById('app-root');
    appRoot.innerHTML = `
      <div style="max-width: 800px; margin: var(--space-8) auto; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-xl); padding: var(--space-8);">
        <h1 style="font-family: var(--font-display); font-size: var(--type-2xl-size); font-weight: 800; margin-bottom: var(--space-4);">DMCA & Copyright Compliance</h1>
        <p style="color: var(--color-text-muted); line-height: 1.7; margin-bottom: var(--space-4);">
          CineStream operates strictly as a media metadata index and user discovery interface. None of the video media files or audio streams are hosted on CineStream servers. Video players utilize standard embedded iframes and open test streams.
        </p>
        <p style="color: var(--color-text-muted); line-height: 1.7; margin-bottom: var(--space-6);">
          If you are a copyright owner or an agent thereof and believe that any metadata, image, or embed link on this site infringes upon your copyright, you may submit a formal notification pursuant to the Digital Millennium Copyright Act (DMCA).
        </p>

        <h3 style="font-size: var(--type-md-size); font-weight: 700; margin-bottom: var(--space-3);">Submit a Takedown Notice</h3>
        <form onsubmit="event.preventDefault(); app.showToast('Takedown inquiry logged. Compliance review underway.', 'success'); this.reset();">
          <div class="form-group">
            <label class="form-label">Infringing URL / Title</label>
            <input type="text" class="form-control" placeholder="https://cinestream.app/movie/title-name" required>
          </div>
          <div class="form-group">
            <label class="form-label">Copyright Holder Name / Organization</label>
            <input type="text" class="form-control" placeholder="Studio / Distributor Name" required>
          </div>
          <div class="form-group">
            <label class="form-label">Contact Email</label>
            <input type="email" class="form-control" placeholder="legal@copyrightowner.com" required>
          </div>
          <button type="submit" class="btn btn-primary btn-md">Submit Compliance Request</button>
        </form>
      </div>
    `;
  }

  // =========================================================================
  // S04: Dedicated Search Results View
  // =========================================================================
  renderSearchResultsPage(query) {
    const q = query.toLowerCase();
    const results = CATALOG_DATA.filter(item => {
      return item.title.toLowerCase().includes(q) ||
             item.genres.some(g => g.toLowerCase().includes(q)) ||
             item.cast.some(c => c.toLowerCase().includes(q));
    });

    const appRoot = document.getElementById('app-root');
    appRoot.innerHTML = `
      <div style="margin-top: var(--space-6);">
        <h1 style="font-family: var(--font-display); font-size: var(--type-xl-size); font-weight: 800; margin-bottom: var(--space-2);">
          Search Results for "<span style="color: var(--color-accent);">${query}</span>"
        </h1>
        <p style="color: var(--color-text-muted); font-size: var(--type-sm-size); margin-bottom: var(--space-6);">Found ${results.length} matching titles</p>

        ${results.length === 0 ? `
          <div style="text-align: center; padding: var(--space-16) 0; color: var(--color-text-muted);">
            <p>No results found matching your query. Check for spelling mistakes or try general terms like "Action" or "Hindi".</p>
            <a href="#/movies" class="btn btn-secondary btn-md" style="margin-top: var(--space-4);">Browse All Movies</a>
          </div>
        ` : `
          <div class="media-grid">
            ${results.map(m => this.renderMediaCard(m)).join('')}
          </div>
        `}
      </div>
    `;
  }

  // =========================================================================
  // S08: Broken Link / Issue Report Modal
  // =========================================================================
  openReportModal(title, activeServer) {
    const modalRoot = document.getElementById('modal-root');
    const modalContent = document.getElementById('modal-content');

    modalContent.innerHTML = `
      <div class="modal-header">
        <h2 class="modal-title">Report Stream Issue</h2>
        <button class="modal-close" onclick="app.closeModal()">&times;</button>
      </div>
      <p style="color: var(--color-text-muted); font-size: var(--type-xs-size); margin-bottom: var(--space-4);">
        Let our engineers know if a video link is dead, buffering, or missing audio tracks.
      </p>
      <form onsubmit="event.preventDefault(); app.submitReport();">
        <div class="form-group">
          <label class="form-label">Affected Title</label>
          <input type="text" class="form-control" value="${title}" readonly>
        </div>
        <div class="form-group">
          <label class="form-label">Active Server</label>
          <input type="text" class="form-control" value="${activeServer}" readonly>
        </div>
        <div class="form-group">
          <label class="form-label">Issue Category</label>
          <select class="form-control" id="report-category">
            <option value="broken_link">Stream not loading / 404 Error</option>
            <option value="audio_sync">Audio out of sync</option>
            <option value="buffering">Excessive buffering lag</option>
            <option value="wrong_movie">Wrong movie / Wrong episode</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Additional Details (Optional)</label>
          <textarea class="form-control" rows="3" placeholder="Tell us what timestamp or error message occurred..."></textarea>
        </div>
        <div style="display: flex; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-4);">
          <button type="button" class="btn btn-secondary btn-md" onclick="app.closeModal()">Cancel</button>
          <button type="submit" class="btn btn-primary btn-md">Submit Issue Report</button>
        </div>
      </form>
    `;

    modalRoot.classList.add('active');
  }

  submitReport() {
    this.closeModal();
    this.showToast('Issue report submitted successfully! Server health check triggered.', 'success');
  }

  // =========================================================================
  // Official Trailer Modal (YouTube Embed)
  // =========================================================================
  openTrailerModal(trailerUrl, title) {
    const modalRoot = document.getElementById('modal-root');
    const modalContent = document.getElementById('modal-content');

    modalContent.innerHTML = `
      <div class="modal-header">
        <h2 class="modal-title">${title} - Official Trailer</h2>
        <button class="modal-close" onclick="app.closeModal()">&times;</button>
      </div>
      <div style="position: relative; width: 100%; aspect-ratio: 16/9; border-radius: var(--radius-md); overflow: hidden; background: #000;">
        <iframe src="${trailerUrl}?autoplay=1" style="width: 100%; height: 100%; border: none;" allow="autoplay; encrypted-media; fullscreen" allowfullscreen></iframe>
      </div>
    `;

    modalRoot.classList.add('active');
  }

  closeModal() {
    const modalRoot = document.getElementById('modal-root');
    if (modalRoot) {
      modalRoot.classList.remove('active');
      const modalContent = document.getElementById('modal-content');
      if (modalContent) modalContent.innerHTML = '';
    }
  }

  // =========================================================================
  // Toast Notification Manager
  // =========================================================================
  showToast(message, type = 'info') {
    const container = document.getElementById('toast-root');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <div style="flex: 1;">${message}</div>
      <button style="color: var(--color-text-muted); cursor: pointer;" onclick="this.parentElement.remove()">&times;</button>
    `;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(20px)';
      toast.style.transition = 'all var(--motion-fast)';
      setTimeout(() => toast.remove(), 200);
    }, 3500);
  }

  // 404 Handler
  renderNotFoundPage() {
    const appRoot = document.getElementById('app-root');
    appRoot.innerHTML = `
      <div style="text-align: center; padding: var(--space-16) 0;">
        <h1 style="font-size: 72px; font-weight: 800; color: var(--color-accent); font-family: var(--font-display);">404</h1>
        <h2 style="font-size: var(--type-xl-size); margin-bottom: var(--space-3);">Page Not Found</h2>
        <p style="color: var(--color-text-muted); margin-bottom: var(--space-6);">The page you requested does not exist or was moved.</p>
        <a href="#/" class="btn btn-primary btn-md">Return to Homepage</a>
      </div>
    `;
  }
}

// Instantiate App
const app = new CineStreamApp();
