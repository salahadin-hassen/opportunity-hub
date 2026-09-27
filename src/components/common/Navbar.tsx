import React from 'react';
import { 
  Sparkles, 
  Bookmark, 
  Compass, 
  FileText, 
  User, 
  Settings, 
  ShieldCheck, 
  Layers
} from 'lucide-react';
import { StudentProfile } from '../../types/opportunity';

export type ActiveTab = 'discover' | 'saved' | 'applications' | 'profile' | 'onboarding-upload' | 'onboarding-review' | 'landing';

interface NavbarProps {
  currentTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  student: StudentProfile;
  savedCount: number;
  onOpenSandbox?: () => void;
  sandboxOpen?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  onTabChange,
  student,
  savedCount,
  onOpenSandbox,
  sandboxOpen
}) => {
  const isOnboarding = currentTab === 'onboarding-upload' || currentTab === 'onboarding-review';
  const isLanding = currentTab === 'landing';

  if (isOnboarding) {
    const stepNumber = currentTab === 'onboarding-upload' ? 1 : 2;
    const progressPercent = currentTab === 'onboarding-upload' ? 20 : 40;

    return (
      <header className="sticky top-0 z-40 bg-white border-b border-gray-100 shadow-subtle">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Left wordmark */}
          <div 
            onClick={() => onTabChange('landing')}
            className="flex items-center gap-2.5 cursor-pointer group"
          >
            <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center text-white shadow-sm group-hover:scale-105 transition-transform">
              <ShieldCheck className="w-5 h-5 text-white" />
            </div>
            <div className="flex flex-col">
              <span className="font-bold text-ink text-lg tracking-tight">Opportunity Hub</span>
              <span className="text-[10px] text-grayText-600 font-mono -mt-1">Verified Matching</span>
            </div>
          </div>

          {/* Right step indicator */}
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-grayText-600">
              Step <span className="text-ink font-semibold">{stepNumber}</span> of 5
            </span>
            <button
              onClick={() => onTabChange('discover')}
              className="text-xs text-grayText-600 hover:text-accent font-medium px-2 py-1 rounded hover:bg-gray-100 transition-colors"
            >
              Skip to app &rarr;
            </button>
          </div>
        </div>

        {/* Thin progress line */}
        <div className="w-full h-1 bg-gray-100">
          <div 
            className="h-full bg-accent transition-all duration-500 ease-out" 
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </header>
    );
  }

  if (isLanding) {
    return (
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div 
            onClick={() => onTabChange('landing')}
            className="flex items-center gap-2.5 cursor-pointer group"
          >
            <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center text-white shadow-sm">
              <ShieldCheck className="w-5 h-5 text-white" />
            </div>
            <div className="flex flex-col">
              <span className="font-bold text-ink text-lg tracking-tight">Opportunity Hub</span>
              <span className="text-[10px] text-grayText-600 font-mono -mt-1">Verified Matching</span>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <button
              onClick={() => onTabChange('discover')}
              className="text-sm font-medium text-grayText-600 hover:text-ink transition-colors"
            >
              Browse Catalog
            </button>
            <button
              onClick={() => onTabChange('onboarding-upload')}
              className="bg-accent hover:bg-accent-hover text-white text-sm font-medium px-4 py-2 rounded-lg shadow-sm transition-all"
            >
              Evaluate My Profile &rarr;
            </button>
          </div>
        </div>
      </header>
    );
  }

  // Persistent Logged-In Top Bar
  return (
    <header className="sticky top-0 z-40 bg-white border-b border-gray-100 shadow-subtle">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        
        {/* Left-aligned wordmark */}
        <div 
          onClick={() => onTabChange('discover')}
          className="flex items-center gap-2.5 cursor-pointer group"
        >
          <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center text-white shadow-sm group-hover:scale-105 transition-transform">
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <div className="flex flex-col">
            <span className="font-bold text-ink text-lg tracking-tight">Opportunity Hub</span>
            <span className="text-[10px] text-grayText-600 font-mono -mt-1">Verified Matching</span>
          </div>
        </div>

        {/* Center top nav: Discover / Saved / Applications / Profile */}
        <nav className="hidden md:flex items-center space-x-1 lg:space-x-2">
          <button
            onClick={() => onTabChange('discover')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${
              currentTab === 'discover'
                ? 'bg-accent-soft text-accent font-semibold'
                : 'text-grayText-600 hover:text-ink hover:bg-surface-50'
            }`}
          >
            <Compass className="w-4 h-4" />
            <span>Discover</span>
          </button>

          <button
            onClick={() => onTabChange('saved')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${
              currentTab === 'saved'
                ? 'bg-accent-soft text-accent font-semibold'
                : 'text-grayText-600 hover:text-ink hover:bg-surface-50'
            }`}
          >
            <Bookmark className="w-4 h-4" />
            <span>Saved</span>
            {savedCount > 0 && (
              <span className={`text-xs px-1.5 py-0.2 rounded-full font-mono ${
                currentTab === 'saved' ? 'bg-accent text-white' : 'bg-gray-100 text-grayText-600'
              }`}>
                {savedCount}
              </span>
            )}
          </button>

          <button
            onClick={() => onTabChange('applications')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${
              currentTab === 'applications'
                ? 'bg-accent-soft text-accent font-semibold'
                : 'text-grayText-600 hover:text-ink hover:bg-surface-50'
            }`}
          >
            <FileText className="w-4 h-4" />
            <span>Applications</span>
          </button>

          <button
            onClick={() => onTabChange('profile')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${
              currentTab === 'profile'
                ? 'bg-accent-soft text-accent font-semibold'
                : 'text-grayText-600 hover:text-ink hover:bg-surface-50'
            }`}
          >
            <User className="w-4 h-4" />
            <span>Profile</span>
          </button>
        </nav>

        {/* Right side: User avatar chip ("AM" initials, "Alex M.") + Settings icon */}
        <div className="flex items-center gap-3">
          {/* Quick Demo Sandbox Trigger */}
          <button
            onClick={onOpenSandbox}
            title="Inspect System States & Demo Flow"
            className={`hidden sm:flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border font-medium transition-all ${
              sandboxOpen 
                ? 'bg-accent text-white border-accent' 
                : 'bg-white border-gray-200 text-grayText-600 hover:text-ink hover:bg-gray-50'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Demo States</span>
          </button>

          {/* User avatar chip */}
          <div 
            onClick={() => onTabChange('profile')}
            className="flex items-center gap-2.5 pl-2 pr-3 py-1.5 rounded-full border border-gray-200 hover:border-accent/40 bg-white hover:bg-accent-soft/40 cursor-pointer transition-all"
          >
            <div className="w-7 h-7 rounded-full bg-accent text-white flex items-center justify-center font-bold text-xs shadow-sm">
              AM
            </div>
            <div className="text-left">
              <p className="text-xs font-semibold text-ink leading-tight">Alex M.</p>
              <p className="text-[10px] text-grayText-600 leading-none font-mono">GPA 3.82</p>
            </div>
          </div>

          {/* Settings icon */}
          <button 
            onClick={() => onTabChange('profile')}
            className="p-2 text-grayText-600 hover:text-ink hover:bg-gray-100 rounded-lg transition-colors"
            title="Account Settings"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>

      </div>

      {/* Mobile nav bar */}
      <div className="md:hidden flex items-center justify-around border-t border-gray-100 px-2 py-1.5 bg-white">
        <button
          onClick={() => onTabChange('discover')}
          className={`flex flex-col items-center py-1 px-3 text-xs ${
            currentTab === 'discover' ? 'text-accent font-semibold' : 'text-grayText-600'
          }`}
        >
          <Compass className="w-4 h-4" />
          <span>Discover</span>
        </button>
        <button
          onClick={() => onTabChange('saved')}
          className={`flex flex-col items-center py-1 px-3 text-xs ${
            currentTab === 'saved' ? 'text-accent font-semibold' : 'text-grayText-600'
          }`}
        >
          <Bookmark className="w-4 h-4" />
          <span>Saved</span>
        </button>
        <button
          onClick={() => onTabChange('applications')}
          className={`flex flex-col items-center py-1 px-3 text-xs ${
            currentTab === 'applications' ? 'text-accent font-semibold' : 'text-grayText-600'
          }`}
        >
          <FileText className="w-4 h-4" />
          <span>Applications</span>
        </button>
        <button
          onClick={() => onTabChange('profile')}
          className={`flex flex-col items-center py-1 px-3 text-xs ${
            currentTab === 'profile' ? 'text-accent font-semibold' : 'text-grayText-600'
          }`}
        >
          <User className="w-4 h-4" />
          <span>Profile</span>
        </button>
      </div>
    </header>
  );
};
