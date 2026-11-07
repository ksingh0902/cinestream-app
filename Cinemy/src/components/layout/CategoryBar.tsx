import React, { useEffect, useState, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  Sparkles,
  Languages,
  Leaf,
  Globe,
  Palette,
  Drama,
  ChevronDown,
  Check,
} from 'lucide-react';
import { getGenres } from '../../api/catalogue';
import { CategoryKey } from '../../types/catalogue';

export interface CategorySelection {
  category: CategoryKey;
  series?: 0 | 1;
  genre?: string;
}

interface CategoryBarProps {
  activeSelection: CategorySelection;
  onSelectCategory: (selection: CategorySelection) => void;
}

// Categories shown directly as top-level navigation tabs
const EXCLUDED_GENRES = new Set([
  'hindi dubbed',
  'hollywood dubbed',
  'punjabi',
  'hollywood',
  'animation',
]);

export const CategoryBar: React.FC<CategoryBarProps> = ({
  activeSelection,
  onSelectCategory,
}) => {
  const [genres, setGenres] = useState<string[]>([]);
  const [selectedDropdownGenre, setSelectedDropdownGenre] = useState<string>('');
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [portalPosition, setPortalPosition] = useState<{ top: number; left: number } | null>(null);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listboxRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    let isMounted = true;
    getGenres()
      .then((data) => {
        if (isMounted) {
          // Filter out genres that already exist as primary category tabs (Hindi Dubbed, Punjabi, Hollywood, Animation)
          const filtered = (data || []).filter(
            (g) => !EXCLUDED_GENRES.has(g.trim().toLowerCase())
          );
          setGenres(filtered);
        }
      })
      .catch(() => {
        if (isMounted) {
          setGenres([
            'Action',
            'Bollywood',
            'South Special',
            'Comedy',
            'Drama',
            'Thriller',
            'Horror',
            'Romance',
            'Crime',
            'Mystery',
            'Sci-fi',
          ]);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // Update fixed portal position based on trigger rect
  const updatePortalPosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setPortalPosition({
      top: rect.bottom + 8,
      left: Math.max(12, Math.min(rect.left, window.innerWidth - 220)),
    });
  }, []);

  // Sync internal state with activeSelection
  useEffect(() => {
    if (!activeSelection.genre) {
      setSelectedDropdownGenre('');
    } else if (activeSelection.category === 'all' && activeSelection.genre) {
      setSelectedDropdownGenre(activeSelection.genre);
    }
  }, [activeSelection]);

  // Recalculate position on open, window resize, and handle clicks/scrolls
  useEffect(() => {
    if (!isDropdownOpen) return;

    updatePortalPosition();

    const handleResize = () => {
      setIsDropdownOpen(false);
      setFocusedIndex(-1);
    };

    // Close only when the outer page scrolls, but allow scrolling inside the dropdown panel itself
    const handleScroll = (e: Event) => {
      if (listboxRef.current && listboxRef.current.contains(e.target as Node)) {
        return; // Allow internal listbox scroll
      }
      setIsDropdownOpen(false);
      setFocusedIndex(-1);
    };

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        triggerRef.current &&
        !triggerRef.current.contains(target) &&
        listboxRef.current &&
        !listboxRef.current.contains(target)
      ) {
        setIsDropdownOpen(false);
        setFocusedIndex(-1);
      }
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('scroll', handleScroll, true);
    document.addEventListener('mousedown', handleClickOutside);

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('scroll', handleScroll, true);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isDropdownOpen, updatePortalPosition]);

  const handleTabClick = (key: CategoryKey) => {
    setSelectedDropdownGenre('');
    setIsDropdownOpen(false);
    switch (key) {
      case 'all':
        onSelectCategory({ category: 'all' });
        break;
      case 'hindi-dubbed':
        onSelectCategory({ category: 'hindi-dubbed', genre: 'Hollywood Dubbed' });
        break;
      case 'punjabi':
        onSelectCategory({ category: 'punjabi', genre: 'Punjabi' });
        break;
      case 'hollywood':
        onSelectCategory({ category: 'hollywood', genre: 'Hollywood' });
        break;
      case 'animation':
        onSelectCategory({ category: 'animation', genre: 'Animation' });
        break;
      case 'movies':
        onSelectCategory({ category: 'movies', series: 0 });
        break;
      case 'series':
        onSelectCategory({ category: 'series', series: 1 });
        break;
    }
  };

  const handleSelectGenre = (genreVal: string) => {
    setSelectedDropdownGenre(genreVal);
    setIsDropdownOpen(false);
    setFocusedIndex(-1);
    if (!genreVal) {
      onSelectCategory({ category: 'all' });
    } else {
      onSelectCategory({
        category: 'all',
        genre: genreVal,
      });
    }
    triggerRef.current?.focus();
  };

  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'ArrowRight') {
      const next = e.currentTarget.nextElementSibling as HTMLElement;
      if (next && next.focus) {
        e.preventDefault();
        next.focus();
      }
    } else if (e.key === 'ArrowLeft') {
      const prev = e.currentTarget.previousElementSibling as HTMLElement;
      if (prev && prev.focus) {
        e.preventDefault();
        prev.focus();
      }
    }
  };

  const handleDropdownTriggerKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      updatePortalPosition();
      setIsDropdownOpen(true);
      const initialIdx = genres.indexOf(selectedDropdownGenre);
      setFocusedIndex(initialIdx >= 0 ? initialIdx + 1 : 0);
      setTimeout(() => listboxRef.current?.focus(), 50);
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setIsDropdownOpen((prev) => {
        const next = !prev;
        if (next) {
          updatePortalPosition();
          const initialIdx = genres.indexOf(selectedDropdownGenre);
          setFocusedIndex(initialIdx >= 0 ? initialIdx + 1 : 0);
          setTimeout(() => listboxRef.current?.focus(), 50);
        } else {
          setFocusedIndex(-1);
        }
        return next;
      });
    } else if (e.key === 'ArrowLeft') {
      const prev = e.currentTarget.previousElementSibling as HTMLElement;
      if (prev && prev.focus) {
        e.preventDefault();
        prev.focus();
      }
    } else if (e.key === 'Escape' && isDropdownOpen) {
      e.preventDefault();
      setIsDropdownOpen(false);
      setFocusedIndex(-1);
    }
  };

  const handleListboxKeyDown = (e: React.KeyboardEvent<HTMLUListElement>) => {
    const totalOptions = genres.length + 1; // +1 for "All Genres"
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusedIndex((prev) => (prev + 1) % totalOptions);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusedIndex((prev) => (prev <= 0 ? totalOptions - 1 : prev - 1));
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (focusedIndex === 0) {
        handleSelectGenre('');
      } else if (focusedIndex > 0 && focusedIndex <= genres.length) {
        handleSelectGenre(genres[focusedIndex - 1]);
      }
    } else if (e.key === 'Escape' || e.key === 'GoBack' || e.key === 'Back' || (e as any).keyCode === 10009) {
      e.preventDefault();
      setIsDropdownOpen(false);
      setFocusedIndex(-1);
      triggerRef.current?.focus();
    } else if (e.key.length === 1 && /[a-zA-Z]/.test(e.key)) {
      // Type to jump
      const char = e.key.toLowerCase();
      const matchIdx = genres.findIndex((g) => g.toLowerCase().startsWith(char));
      if (matchIdx >= 0) {
        setFocusedIndex(matchIdx + 1);
      }
    }
  };

  // Scroll focused option into view smoothly for TV navigation
  useEffect(() => {
    if (isDropdownOpen && focusedIndex >= 0 && listboxRef.current) {
      const items = listboxRef.current.querySelectorAll<HTMLLIElement>('.genre-dropdown-item');
      if (items[focusedIndex]) {
        items[focusedIndex].scrollIntoView({ block: 'nearest' });
      }
    }
  }, [focusedIndex, isDropdownOpen]);

  const isDropdownActive = Boolean(
    selectedDropdownGenre && !activeSelection.series && !EXCLUDED_GENRES.has(selectedDropdownGenre.toLowerCase())
  );
  const displayGenreLabel =
    selectedDropdownGenre && !EXCLUDED_GENRES.has(selectedDropdownGenre.toLowerCase())
      ? selectedDropdownGenre
      : 'Genre';

  return (
    <div className="category-bar-wrapper">
      <nav className="category-bar-inner" aria-label="Content Categories">
        <button
          type="button"
          className={`category-tab ${activeSelection.category === 'all' && !activeSelection.genre ? 'active' : ''}`}
          onClick={() => handleTabClick('all')}
          onKeyDown={handleTabKeyDown}
        >
          <Sparkles size={15} strokeWidth={1.5} className="tab-icon" />
          <span>All Titles</span>
        </button>

        <button
          type="button"
          className={`category-tab ${activeSelection.category === 'hindi-dubbed' ? 'active' : ''}`}
          onClick={() => handleTabClick('hindi-dubbed')}
          onKeyDown={handleTabKeyDown}
        >
          <Languages size={15} strokeWidth={1.5} className="tab-icon" />
          <span>Hindi Dubbed</span>
        </button>

        <button
          type="button"
          className={`category-tab ${activeSelection.category === 'punjabi' ? 'active' : ''}`}
          onClick={() => handleTabClick('punjabi')}
          onKeyDown={handleTabKeyDown}
        >
          <Leaf size={15} strokeWidth={1.5} className="tab-icon" />
          <span>Punjabi</span>
        </button>

        <button
          type="button"
          className={`category-tab ${activeSelection.category === 'hollywood' ? 'active' : ''}`}
          onClick={() => handleTabClick('hollywood')}
          onKeyDown={handleTabKeyDown}
        >
          <Globe size={15} strokeWidth={1.5} className="tab-icon" />
          <span>Hollywood</span>
        </button>

        <button
          type="button"
          className={`category-tab ${activeSelection.category === 'animation' ? 'active' : ''}`}
          onClick={() => handleTabClick('animation')}
          onKeyDown={handleTabKeyDown}
        >
          <Palette size={15} strokeWidth={1.5} className="tab-icon" />
          <span>Animation</span>
        </button>

        {/* Custom Accessible Genre Dropdown */}
        <div className="genre-dropdown-container" ref={dropdownRef}>
          <button
            ref={triggerRef}
            type="button"
            className={`category-tab genre-dropdown-trigger ${isDropdownActive ? 'active' : ''}`}
            onClick={() => {
              updatePortalPosition();
              setIsDropdownOpen((prev) => !prev);
            }}
            onKeyDown={handleDropdownTriggerKeyDown}
            aria-haspopup="listbox"
            aria-expanded={isDropdownOpen}
            aria-label={`Filter by genre. Currently selected: ${displayGenreLabel}`}
          >
            <Drama size={15} strokeWidth={1.5} className="tab-icon" />
            <span className="genre-trigger-text">{displayGenreLabel}</span>
            <ChevronDown
              size={13}
              strokeWidth={1.5}
              className={`select-chevron ${isDropdownOpen ? 'rotated' : ''}`}
            />
          </button>
        </div>
      </nav>

      {/* Render Dropdown in Portal attached to document.body */}
      {isDropdownOpen &&
        createPortal(
          <>
            <div
              className="genre-dropdown-backdrop"
              onClick={() => {
                setIsDropdownOpen(false);
                setFocusedIndex(-1);
              }}
            />
            <ul
              ref={listboxRef}
              className="genre-dropdown-panel"
              role="listbox"
              tabIndex={0}
              onKeyDown={handleListboxKeyDown}
              aria-label="Select Genre"
              style={
                portalPosition && window.innerWidth > 768
                  ? {
                      top: `${portalPosition.top}px`,
                      left: `${portalPosition.left}px`,
                    }
                  : undefined
              }
            >
              {/* Reset to All Genres Option */}
              <li
                role="option"
                aria-selected={!selectedDropdownGenre}
                className={`genre-dropdown-item ${!selectedDropdownGenre ? 'selected' : ''} ${focusedIndex === 0 ? 'focused' : ''}`}
                onClick={() => handleSelectGenre('')}
                onMouseEnter={() => setFocusedIndex(0)}
              >
                <span>All Genres</span>
                {!selectedDropdownGenre && (
                  <Check size={14} strokeWidth={2} className="genre-check-icon" />
                )}
              </li>

              {/* Dynamic Genre Options without duplicate top nav tabs */}
              {genres.map((g, idx) => {
                const itemIndex = idx + 1;
                const isSelected = selectedDropdownGenre === g;
                const isFocused = focusedIndex === itemIndex;
                return (
                  <li
                    key={g}
                    role="option"
                    aria-selected={isSelected}
                    className={`genre-dropdown-item ${isSelected ? 'selected' : ''} ${isFocused ? 'focused' : ''}`}
                    onClick={() => handleSelectGenre(g)}
                    onMouseEnter={() => setFocusedIndex(itemIndex)}
                  >
                    <span>{g}</span>
                    {isSelected && (
                      <Check size={14} strokeWidth={2} className="genre-check-icon" />
                    )}
                  </li>
                );
              })}
            </ul>
          </>,
          document.body
        )}
    </div>
  );
};
