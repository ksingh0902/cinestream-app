import React, { useState, useEffect, useRef, lazy, Suspense } from 'react';
import { Lock } from 'lucide-react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { RouterProvider, useRouter } from './router';
import { AppLayout } from './components/layout/AppLayout';
import { CategorySelection } from './components/layout/CategoryBar';
import { LoadingSpinner } from './components/common/LoadingSpinner';
import { ErrorBanner } from './components/common/ErrorBanner';
import { HomePage } from './components/home/HomePage';
import { MovieDetailPage } from './features/movie-details';
import { SeriesDetailPage } from './features/series-details';
import { MyListPage } from './features/watchlist';
import { SearchPage } from './features/search';
import { GenrePage } from './features/catalogue';
import { ProfilePage } from './features/profile';
import { PlaybackTarget, PlayerModal } from './features/player';
import { useTVNav } from './hooks/useTVNav';

// Lazy-load AdminConsolePage so standard viewers never download administrative chunks
const AdminConsolePage = lazy(() =>
  import('./features/admin').then((m) => ({ default: m.AdminConsolePage }))
);

export const AppContent: React.FC = () => {
  const { loading: authLoading, error: authError, isStorageOutage, refreshAuth, authenticated } = useAuth();
  const { path, matchRoute, navigate, back } = useRouter();

  const [activeCategory, setActiveCategory] = useState<CategorySelection>({ category: 'all' });
  const [playerTarget, setPlayerTarget] = useState<PlaybackTarget | null>(null);
  const playerTriggerRef = useRef<HTMLElement | null>(null);

  // Hook up Smart TV remote spatial navigation and escape/back handling
  useTVNav({
    onBack: back,
    isPlayerOpen: Boolean(playerTarget),
  });

  // Smart TV: Automatic Initial Focus on Route Transitions
  useEffect(() => {
    // Only focus if there is no active focused element, or if focus is resting on body/html
    const timer = setTimeout(() => {
      const active = document.activeElement;
      if (!active || active === document.body || active === document.documentElement) {
        // Only focus dedicated detail navigation buttons on detail page routes
        // Do NOT focus category tabs on page load to prevent unwanted focus borders/outlines
        const initialEl = document.querySelector<HTMLElement>(
          '.btn-nav-back, .btn-play-large'
        );
        if (initialEl && initialEl.focus) {
          initialEl.focus({ preventScroll: true });
        }
      }
    }, 120);

    return () => clearTimeout(timer);
  }, [path]);

  const handleOpenPlayer = (target: PlaybackTarget) => {
    playerTriggerRef.current = document.activeElement as HTMLElement | null;
    setPlayerTarget(target);
  };

  const handleClosePlayer = () => {
    setPlayerTarget(null);
    // Focus restoration
    setTimeout(() => {
      if (playerTriggerRef.current && document.body.contains(playerTriggerRef.current)) {
        playerTriggerRef.current.focus();
      } else {
        const fallback = document.querySelector<HTMLElement>('.btn-play-large, .category-tab.active, .content-card');
        fallback?.focus();
      }
    }, 50);
  };

  const handleHomeClick = () => {
    setActiveCategory({ category: 'all', resetToken: Date.now() });
    navigate('/');
  };

  const handleSelectFromSearch = (id: number) => {
    navigate(`/movie/${id}`);
  };

  if (authLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <LoadingSpinner label="Connecting to CineMyMovies..." size="lg" />
      </div>
    );
  }

  // Route Pattern Matching
  const movieMatch = matchRoute('/movie/:movieId');
  const seriesMatch = matchRoute('/series/:seriesId');
  const genreMatch = matchRoute('/genre/:genreName');

  const isDetailPage = movieMatch.matches || seriesMatch.matches || genreMatch.matches;
  const isUtilityPage = path === '/my-list' || path === '/search' || path === '/profile' || path === '/admin';
  const showCategoryBar = !isDetailPage && !isUtilityPage;

  return (
    <AppLayout
      activeCategory={activeCategory}
      onSelectCategory={(selection) => {
        setActiveCategory(selection);
        if (selection.category === 'all' && !selection.genre) {
          if (path !== '/') {
            navigate('/');
          }
        } else if (path !== '/' && path !== '/movies' && path !== '/series') {
          navigate('/');
        }
      }}
      onHomeClick={handleHomeClick}
      onSelectMovie={handleSelectFromSearch}
      showCategoryBar={showCategoryBar}
    >
      {/* Service Outage or Auth Warning */}
      {isStorageOutage && (
        <ErrorBanner
          message="Authentication storage is currently unavailable. Protected features may be limited."
          isOutage={true}
          onRetry={refreshAuth}
        />
      )}

      {authError && !isStorageOutage && (
        <ErrorBanner message={authError} onRetry={refreshAuth} />
      )}

      {/* Unauthenticated Notification (Guest Mode) */}
      {!authenticated && !isStorageOutage && (
        <div
          style={{
            background: 'var(--card)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            padding: '12px 16px',
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '8px',
          }}
        >
          <span style={{ fontSize: '13px', color: 'var(--dim)' }}>
            <Lock size={13} strokeWidth={1.5} style={{ verticalAlign: "middle", marginRight: 6 }} /> You are browsing in guest mode. Sign in to access your personal account and all streams.
          </span>
          <a href="/login" className="btn btn-primary" style={{ padding: '4px 12px', fontSize: '12px' }}>
            Sign In
          </a>
        </div>
      )}

      {/* Dynamic View Router */}
      {movieMatch.matches && (
        <MovieDetailPage
          movieId={Number(movieMatch.params.movieId)}
          onPlayTarget={handleOpenPlayer}
        />
      )}

      {seriesMatch.matches && (
        <SeriesDetailPage
          seriesId={Number(seriesMatch.params.seriesId)}
          onPlayTarget={handleOpenPlayer}
        />
      )}

      {genreMatch.matches && (
        <GenrePage genreName={genreMatch.params.genreName} />
      )}

      {path === '/my-list' && <MyListPage />}

      {path === '/search' && <SearchPage />}

      {path === '/profile' && <ProfilePage />}

      {path === '/admin' && (
        <Suspense
          fallback={
            <div style={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <LoadingSpinner label="Loading Admin Console..." size="md" />
            </div>
          }
        >
          <AdminConsolePage />
        </Suspense>
      )}

      {path === '/movies' && (
        <HomePage
          activeCategory={{ category: 'movies', series: 0 }}
          onResetCategory={() => setActiveCategory({ category: 'all' })}
          onSelectCategory={setActiveCategory}
          onPlayTarget={handleOpenPlayer}
        />
      )}

      {path === '/series' && (
        <HomePage
          activeCategory={{ category: 'series', series: 1 }}
          onResetCategory={() => setActiveCategory({ category: 'all' })}
          onSelectCategory={setActiveCategory}
          onPlayTarget={handleOpenPlayer}
        />
      )}

      {/* Default / Home View */}
      {path === '/' && !isDetailPage && !isUtilityPage && (
        <HomePage
          activeCategory={activeCategory}
          onResetCategory={() => setActiveCategory({ category: 'all' })}
          onSelectCategory={setActiveCategory}
          onPlayTarget={handleOpenPlayer}
        />
      )}

      {/* React Streaming Player Modal */}
      <PlayerModal
        isOpen={Boolean(playerTarget)}
        target={playerTarget}
        onClose={handleClosePlayer}
      />
    </AppLayout>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <RouterProvider>
        <AppContent />
      </RouterProvider>
    </AuthProvider>
  );
};

export default App;
