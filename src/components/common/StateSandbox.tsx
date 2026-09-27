import React from 'react';
import { 
  X, 
  Sparkles, 
  CheckCircle2, 
  AlertTriangle, 
  XCircle, 
  FileUp, 
  CheckSquare, 
  LayoutDashboard, 
  FileSearch, 
  Bookmark, 
  User, 
  Home,
  SlidersHorizontal,
  Flame
} from 'lucide-react';
import { ActiveTab } from './Navbar';

interface StateSandboxProps {
  isOpen: boolean;
  onClose: () => void;
  currentTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  onSelectOpportunity: (oppId: string) => void;
  demoEmptyState: boolean;
  onToggleDemoEmptyState: () => void;
  systemStateOverlay: string | null;
  onSetSystemStateOverlay: (state: string | null) => void;
}

export const StateSandbox: React.FC<StateSandboxProps> = ({
  isOpen,
  onClose,
  currentTab,
  onTabChange,
  onSelectOpportunity,
  demoEmptyState,
  onToggleDemoEmptyState,
  systemStateOverlay,
  onSetSystemStateOverlay
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 w-96 bg-white border border-gray-200 rounded-2xl shadow-floating p-4 transition-all animate-in fade-in slide-in-from-bottom-3 duration-200">
      <div className="flex items-center justify-between border-b border-gray-100 pb-3 mb-3">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-accent flex items-center justify-center text-white">
            <SlidersHorizontal className="w-3.5 h-3.5" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-ink">Demo Navigator & State Tester</h4>
            <p className="text-[10px] text-grayText-600">Switch screens & test system states</p>
          </div>
        </div>
        <button 
          onClick={onClose}
          className="p-1 rounded-md text-grayText-400 hover:text-ink hover:bg-gray-100"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-3">
        {/* Core Demo Loop (1 -> 2 -> 3 -> 4) */}
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-accent font-mono block mb-1.5">
            1. Core Demo Loop (Upload &rarr; Confirm &rarr; Match &rarr; Detail)
          </span>
          <div className="grid grid-cols-2 gap-1.5">
            <button
              onClick={() => { onTabChange('onboarding-upload'); onClose(); }}
              className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs font-medium border text-left transition-colors ${
                currentTab === 'onboarding-upload' ? 'bg-accent-soft border-accent text-accent' : 'border-gray-200 hover:bg-gray-50 text-ink'
              }`}
            >
              <FileUp className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate">1. Document Upload</span>
            </button>
            <button
              onClick={() => { onTabChange('onboarding-review'); onClose(); }}
              className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs font-medium border text-left transition-colors ${
                currentTab === 'onboarding-review' ? 'bg-accent-soft border-accent text-accent' : 'border-gray-200 hover:bg-gray-50 text-ink'
              }`}
            >
              <CheckSquare className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate">2. Extraction Review</span>
            </button>
            <button
              onClick={() => { onTabChange('discover'); onClose(); }}
              className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs font-medium border text-left transition-colors ${
                currentTab === 'discover' && !demoEmptyState ? 'bg-accent-soft border-accent text-accent' : 'border-gray-200 hover:bg-gray-50 text-ink'
              }`}
            >
              <LayoutDashboard className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate">3. Dashboard</span>
            </button>
            <button
              onClick={() => { onSelectOpportunity('chevening-2027'); onClose(); }}
              className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs font-medium border border-gray-200 hover:bg-gray-50 text-ink text-left transition-colors"
            >
              <FileSearch className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
              <span className="truncate">4. Detail (Eligible)</span>
            </button>
          </div>
        </div>

        {/* Opportunity Detail Scenarios */}
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-grayText-600 font-mono block mb-1.5">
            2. Match Matrix Scenarios (Screen 4)
          </span>
          <div className="grid grid-cols-3 gap-1">
            <button
              onClick={() => { onSelectOpportunity('chevening-2027'); onClose(); }}
              className="flex items-center gap-1 px-1.5 py-1 rounded border border-emerald-200 bg-emerald-50/50 hover:bg-emerald-100 text-[11px] text-emerald-900 font-medium"
            >
              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
              <span className="truncate">Chevening (✓)</span>
            </button>
            <button
              onClick={() => { onSelectOpportunity('mastercard-scholars-2027'); onClose(); }}
              className="flex items-center gap-1 px-1.5 py-1 rounded border border-rose-200 bg-rose-50/50 hover:bg-rose-100 text-[11px] text-rose-900 font-medium"
            >
              <XCircle className="w-3 h-3 text-rose-600" />
              <span className="truncate">Mastercard (✕ Near)</span>
            </button>
            <button
              onClick={() => { onSelectOpportunity('daad-rise-2026'); onClose(); }}
              className="flex items-center gap-1 px-1.5 py-1 rounded border border-amber-200 bg-amber-50/50 hover:bg-amber-100 text-[11px] text-amber-900 font-medium"
            >
              <AlertTriangle className="w-3 h-3 text-amber-600" />
              <span className="truncate">DAAD (⚠ Lang)</span>
            </button>
          </div>
        </div>

        {/* Other Pages */}
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-grayText-600 font-mono block mb-1.5">
            3. Other Screens (5, 6, 7)
          </span>
          <div className="grid grid-cols-3 gap-1.5">
            <button
              onClick={() => { onTabChange('saved'); onClose(); }}
              className={`flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-medium border text-left ${
                currentTab === 'saved' ? 'bg-accent-soft border-accent text-accent' : 'border-gray-200 hover:bg-gray-50 text-ink'
              }`}
            >
              <Bookmark className="w-3.5 h-3.5 shrink-0" />
              <span>5. Saved</span>
            </button>
            <button
              onClick={() => { onTabChange('profile'); onClose(); }}
              className={`flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-medium border text-left ${
                currentTab === 'profile' ? 'bg-accent-soft border-accent text-accent' : 'border-gray-200 hover:bg-gray-50 text-ink'
              }`}
            >
              <User className="w-3.5 h-3.5 shrink-0" />
              <span>6. Profile</span>
            </button>
            <button
              onClick={() => { onTabChange('landing'); onClose(); }}
              className={`flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-medium border text-left ${
                currentTab === 'landing' ? 'bg-accent-soft border-accent text-accent' : 'border-gray-200 hover:bg-gray-50 text-ink'
              }`}
            >
              <Home className="w-3.5 h-3.5 shrink-0" />
              <span>7. Landing</span>
            </button>
          </div>
        </div>

        {/* System States Toggles (8) */}
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-grayText-600 font-mono block mb-1.5">
            4. System States Overlay (Screen 8)
          </span>
          <div className="flex flex-wrap gap-1">
            <button
              onClick={() => onToggleDemoEmptyState()}
              className={`px-2 py-1 rounded text-[11px] font-medium border ${
                demoEmptyState ? 'bg-ink text-white border-ink' : 'border-gray-200 hover:bg-gray-100 text-gray-700'
              }`}
            >
              Toggle Empty Profile State
            </button>
            <button
              onClick={() => onSetSystemStateOverlay(systemStateOverlay === 'loading' ? null : 'loading')}
              className={`px-2 py-1 rounded text-[11px] font-medium border ${
                systemStateOverlay === 'loading' ? 'bg-accent text-white border-accent' : 'border-gray-200 hover:bg-gray-100 text-gray-700'
              }`}
            >
              Loading Modal
            </button>
            <button
              onClick={() => onSetSystemStateOverlay(systemStateOverlay === 'error' ? null : 'error')}
              className={`px-2 py-1 rounded text-[11px] font-medium border ${
                systemStateOverlay === 'error' ? 'bg-rose-600 text-white border-rose-600' : 'border-gray-200 hover:bg-gray-100 text-gray-700'
              }`}
            >
              Error State
            </button>
            <button
              onClick={() => onSetSystemStateOverlay(systemStateOverlay === 'upload_failed' ? null : 'upload_failed')}
              className={`px-2 py-1 rounded text-[11px] font-medium border ${
                systemStateOverlay === 'upload_failed' ? 'bg-rose-600 text-white border-rose-600' : 'border-gray-200 hover:bg-gray-100 text-gray-700'
              }`}
            >
              Upload Failed Alert
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
