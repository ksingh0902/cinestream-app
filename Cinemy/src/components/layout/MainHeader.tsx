import React, { useState, useEffect, useRef } from 'react';
import {
  House,
  Clapperboard,
  Tv,
  Bookmark,
  Search,
  UserRound,
  Settings,
  LogOut,
  ChevronDown,
  X,
  Star,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useDebounce } from '../../hooks/useDebounce';
import { searchTitles } from '../../api/catalogue';
import { SearchItem } from '../../types/catalogue';
import { formatRating } from '../../utils/formatters';
import { useRouter } from '../../router';
import { CategoryBar, CategorySelection } from './CategoryBar';

interface MainHeaderProps {
  onHomeClick?: () => void;
  onSelectMovie?: (id: number) => void;
  activeCategory?: CategorySelection;
  onSelectCategory?: (selection: CategorySelection) => void;
  showCategoryBar?: boolean;
}

export const MainHeader: React.FC<MainHeaderProps> = ({
  onHomeClick,
  onSelectMovie,
  activeCategory,
  onSelectCategory,
  showCategoryBar = false,
}) => {
  const { authenticated, username, role, logout } = useAuth();
  const { path, navigate } = useRouter();

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);
  const [isScrolled, setIsScrolled] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  const debouncedQuery = useDebounce(query, 300);
  const searchWrapRef = useRef<HTMLDivElement>(null);
  const profileMenuRef = useRef<HTMLDivElement>(null);

  // Monitor scroll for frosted glass appearance
  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Close search dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchWrapRef.current && !searchWrapRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target as Node)) {
        setIsProfileOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Fetch search suggestions
  useEffect(() => {
    const trimmed = debouncedQuery.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setIsLoading(false);
      return;
    }

    let isCurrent = true;
    setIsLoading(true);

    searchTitles(trimmed, 8)
      .then((res) => {
        if (!isCurrent) return;
        setResults(res.items || []);
        setIsOpen(true);
        setSelectedIndex(-1);
      })
      .catch(() => {
        if (!isCurrent) return;
        setResults([]);
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [debouncedQuery]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      setIsOpen(false);
      setSelectedIndex(-1);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen && results.length > 0) {
        setIsOpen(true);
      } else if (results.length > 0) {
        setSelectedIndex((prev) => (prev + 1) % results.length);
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (results.length > 0) {
        setSelectedIndex((prev) => (prev <= 0 ? results.length - 1 : prev - 1));
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (selectedIndex >= 0 && selectedIndex < results.length) {
        const selected = results[selectedIndex];
        handleSelect(selected.id, Boolean(selected.is_series));
      } else if (query.trim()) {
        setIsOpen(false);
        navigate(`/search?q=${encodeURIComponent(query.trim())}`);
      }
    }
  };

  const handleSelect = (id: number, isSeries?: boolean) => {
    setIsOpen(false);
    setQuery('');
    if (onSelectMovie) {
      onSelectMovie(id);
    } else {
      navigate(isSeries ? `/series/${id}` : `/movie/${id}`);
    }
  };

  const handleClear = () => {
    setQuery('');
    setResults([]);
    setIsOpen(false);
  };

  const handleBrandClick = () => {
    if (onHomeClick) {
      onHomeClick();
    } else {
      navigate('/');
    }
  };

  const isNavActive = (target: string) => {
    if (target === '/') return path === '/';
    return path.startsWith(target);
  };

  return (
    <>
      <header className={`main-header ${isScrolled ? 'scrolled' : 'transparent'}`}>
        <div className="header-inner">
          {/* Left: Brand & Desktop Navigation */}
          <div className="header-left-group">
            <div
              className="header-brand"
              onClick={handleBrandClick}
              tabIndex={0}
              role="button"
              onKeyDown={(e) => e.key === 'Enter' && handleBrandClick()}
              title="CINEMY Home"
            >
              <div className="brand-logo-badge">
                <svg
                  className="header-logo-icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polygon points="5 3 19 12 5 21 5 3" fill="currentColor" />
                </svg>
              </div>
              <span className="header-title">CINEMY</span>
            </div>

            {/* Desktop Navigation Links */}
            <nav className="header-nav-links" aria-label="Main Navigation">
              <button
                type="button"
                className={`header-nav-btn ${isNavActive('/') && path === '/' ? 'active' : ''}`}
                onClick={() => navigate('/')}
              >
                <House size={16} strokeWidth={1.5} className="nav-btn-icon" />
                <span>Home</span>
              </button>
              <button
                type="button"
                className={`header-nav-btn ${isNavActive('/movies') ? 'active' : ''}`}
                onClick={() => navigate('/movies')}
              >
                <Clapperboard size={16} strokeWidth={1.5} className="nav-btn-icon" />
                <span>Movies</span>
              </button>
              <button
                type="button"
                className={`header-nav-btn ${isNavActive('/series') ? 'active' : ''}`}
                onClick={() => navigate('/series')}
              >
                <Tv size={16} strokeWidth={1.5} className="nav-btn-icon" />
                <span>Series</span>
              </button>
              <button
                type="button"
                className={`header-nav-btn ${isNavActive('/my-list') ? 'active' : ''}`}
                onClick={() => navigate('/my-list')}
              >
                <Bookmark size={16} strokeWidth={1.5} className="nav-btn-icon" />
                <span>My List</span>
              </button>
            </nav>
          </div>

          {/* Center: Search Area */}
          <div className="header-search" ref={searchWrapRef}>
            <div className="search-box">
              <Search
                size={16}
                strokeWidth={1.5}
                className="search-icon"
                onClick={() =>
                  navigate(query.trim() ? `/search?q=${encodeURIComponent(query.trim())}` : '/search')
                }
                aria-label="Open Search"
                role="button"
                tabIndex={0}
              />
              <input
                type="search"
                className="search-input"
                placeholder="Search movies & series..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => query.trim().length >= 2 && setIsOpen(true)}
                onKeyDown={handleKeyDown}
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="none"
                enterKeyHint="search"
              />
              {isLoading && <div className="search-spinner-inline" aria-label="Searching..." />}
              {!isLoading && query && (
                <button
                  type="button"
                  className="search-clear-btn"
                  onClick={handleClear}
                  title="Clear search"
                  aria-label="Clear search"
                >
                  <X size={14} strokeWidth={1.5} />
                </button>
              )}
            </div>

            {/* Search Dropdown Suggestions */}
            {isOpen && (
              <div className="search-dropdown" role="listbox">
                {results.length > 0 ? (
                  results.map((item, index) => {
                    const ratingBadge = formatRating(null, item.imdb);
                    const isItemSeries = Boolean(item.is_series);
                    return (
                      <div
                        key={item.id}
                        className={`search-item ${index === selectedIndex ? 'active' : ''}`}
                        role="option"
                        aria-selected={index === selectedIndex}
                        tabIndex={0}
                        onClick={() => handleSelect(item.id, isItemSeries)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSelect(item.id, isItemSeries)}
                      >
                        <img
                          className="search-item-poster"
                          src={item.poster || '/favicon.svg'}
                          alt={item.title}
                          loading="lazy"
                        />
                        <div className="search-item-info">
                          <div className="search-item-title">{item.title}</div>
                          <div className="search-item-meta">
                            <span className="search-item-type">{isItemSeries ? 'Series' : 'Movie'}</span>
                            {item.year && <span>• {item.year}</span>}
                            {ratingBadge && (
                              <span className="search-item-rating">
                                <Star size={11} strokeWidth={1.5} fill="currentColor" style={{ verticalAlign: 'middle', marginRight: 3 }} />
                                {ratingBadge}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="search-empty">
                    {isLoading ? 'Searching catalogue...' : `No titles found matching "${query}"`}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right: User Avatar & Profile Dropdown */}
          <div className="header-actions">
            {authenticated && username ? (
              <div className="profile-menu-container" ref={profileMenuRef}>
                <button
                  type="button"
                  className={`header-avatar-btn ${isProfileOpen ? 'open' : ''}`}
                  onClick={() => setIsProfileOpen((prev) => !prev)}
                  aria-expanded={isProfileOpen}
                  aria-haspopup="true"
                  title={`Signed in as ${username}`}
                >
                  <div className="avatar-icon-wrap">
                    <UserRound size={17} strokeWidth={1.5} />
                  </div>
                  <span className="avatar-username hide-on-mobile">{username}</span>
                  {role && <span className={`role-pill ${role}`}>{role}</span>}
                  <ChevronDown
                    size={13}
                    strokeWidth={1.5}
                    className={`avatar-chevron ${isProfileOpen ? 'rotate' : ''}`}
                  />
                </button>

                {/* Profile Dropdown Menu */}
                {isProfileOpen && (
                  <div className="profile-dropdown-card" role="menu">
                    <div className="profile-dropdown-user-info">
                      <div className="profile-dropdown-display-name">{username}</div>
                      <div className="profile-dropdown-role-label">
                        Role: <span className="profile-role-text">{role || 'viewer'}</span>
                      </div>
                    </div>

                    <div className="profile-dropdown-nav">
                      <button
                        type="button"
                        className="profile-dropdown-link"
                        role="menuitem"
                        onClick={() => {
                          setIsProfileOpen(false);
                          navigate('/profile');
                        }}
                      >
                        <UserRound size={15} strokeWidth={1.5} />
                        <span>My Profile</span>
                      </button>

                      {role === 'admin' && (
                        <button
                          type="button"
                          className="profile-dropdown-link"
                          role="menuitem"
                          onClick={() => {
                            setIsProfileOpen(false);
                            navigate('/admin');
                          }}
                        >
                          <Settings size={15} strokeWidth={1.5} />
                          <span>Admin Console</span>
                        </button>
                      )}

                      <div className="profile-dropdown-divider" />

                      <button
                        type="button"
                        className="profile-dropdown-link logout-btn"
                        role="menuitem"
                        onClick={() => {
                          setIsProfileOpen(false);
                          logout();
                        }}
                      >
                        <LogOut size={15} strokeWidth={1.5} />
                        <span>Sign Out</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <a href="/login" className="btn btn-primary btn-sign-in">
                Sign In
              </a>
            )}
          </div>
        </div>

        {/* Integrated Category Navigation Tab Strip */}
        {showCategoryBar && activeCategory && onSelectCategory && (
          <CategoryBar
            activeSelection={activeCategory}
            onSelectCategory={onSelectCategory}
          />
        )}
      </header>

      {/* Mobile Bottom Navigation Bar */}
      <nav className="mobile-bottom-nav" aria-label="Mobile Navigation">
        <button
          type="button"
          className={`mobile-nav-item ${path === '/' ? 'active' : ''}`}
          onClick={() => navigate('/')}
        >
          <House size={20} strokeWidth={1.5} className="mobile-nav-icon" />
          <span className="nav-label">Home</span>
        </button>
        <button
          type="button"
          className={`mobile-nav-item ${path === '/movies' ? 'active' : ''}`}
          onClick={() => navigate('/movies')}
        >
          <Clapperboard size={20} strokeWidth={1.5} className="mobile-nav-icon" />
          <span className="nav-label">Movies</span>
        </button>
        <button
          type="button"
          className={`mobile-nav-item ${path === '/series' ? 'active' : ''}`}
          onClick={() => navigate('/series')}
        >
          <Tv size={20} strokeWidth={1.5} className="mobile-nav-icon" />
          <span className="nav-label">Series</span>
        </button>
        <button
          type="button"
          className={`mobile-nav-item ${path === '/my-list' ? 'active' : ''}`}
          onClick={() => navigate('/my-list')}
        >
          <Bookmark size={20} strokeWidth={1.5} className="mobile-nav-icon" />
          <span className="nav-label">My List</span>
        </button>
        <button
          type="button"
          className={`mobile-nav-item ${path === '/search' ? 'active' : ''}`}
          onClick={() => navigate('/search')}
        >
          <Search size={20} strokeWidth={1.5} className="mobile-nav-icon" />
          <span className="nav-label">Search</span>
        </button>
        <button
          type="button"
          className={`mobile-nav-item ${path === '/profile' ? 'active' : ''}`}
          onClick={() => navigate('/profile')}
        >
          <UserRound size={20} strokeWidth={1.5} className="mobile-nav-icon" />
          <span className="nav-label">Profile</span>
        </button>
      </nav>
    </>
  );
};
