import React from 'react';
import { MainHeader } from './MainHeader';
import { CategorySelection } from './CategoryBar';

interface AppLayoutProps {
  children: React.ReactNode;
  activeCategory: CategorySelection;
  onSelectCategory: (selection: CategorySelection) => void;
  onHomeClick?: () => void;
  onSelectMovie?: (id: number) => void;
  showCategoryBar?: boolean;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  children,
  activeCategory,
  onSelectCategory,
  onHomeClick,
  onSelectMovie,
  showCategoryBar = true,
}) => {
  return (
    <div className="app-container">
      <MainHeader
        onHomeClick={onHomeClick}
        onSelectMovie={onSelectMovie}
        activeCategory={activeCategory}
        onSelectCategory={onSelectCategory}
        showCategoryBar={showCategoryBar}
      />
      <main className="main-content">{children}</main>
    </div>
  );
};
