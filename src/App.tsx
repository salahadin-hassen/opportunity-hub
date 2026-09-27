import React, { useState } from 'react';
import { seedStudent } from './data/seedStudent';
import { seedOpportunities } from './data/seedOpportunities';
import { 
  StudentProfile, 
  Opportunity, 
  ApplicationProgress 
} from './types/opportunity';
import { Navbar, ActiveTab } from './components/common/Navbar';
import { DocumentUpload } from './components/onboarding/DocumentUpload';
import { ExtractionReview } from './components/onboarding/ExtractionReview';
import { DashboardView } from './components/dashboard/DashboardView';
import { OpportunityDetail } from './components/detail/OpportunityDetail';
import { SavedView } from './components/saved/SavedView';
import { ProfileView } from './components/profile/ProfileView';
import { LandingPage } from './components/landing/LandingPage';
import { StateSandbox } from './components/common/StateSandbox';
import { 
  LoadingState, 
  ErrorState, 
  UploadFailedState
} from './components/common/SystemStates';
import { X } from 'lucide-react';

export const App: React.FC = () => {
  // Navigation & Screen selection
  // The user prompt requested: "BUILD THIS FLOW, IN THIS ORDER: 1. Document upload -> 2. Extraction confirmation -> 3. Dashboard -> 4. Opportunity detail"
  // Let's start on 'onboarding-upload' so the reviewer lands directly in Step 1 of the requested demo loop!
  const [currentTab, setCurrentTab] = useState<ActiveTab>('onboarding-upload');
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<string | null>(null);

  // Core App State
  const [student, setStudent] = useState<StudentProfile>(seedStudent);
  const [opportunities] = useState<Opportunity[]>(seedOpportunities);
  const [savedOpportunityIds, setSavedOpportunityIds] = useState<string[]>([
    'chevening-2027',
    'fulbright-2026'
  ]);
  const [applicationStatuses, setApplicationStatuses] = useState<Record<string, ApplicationProgress>>({
    'chevening-2027': 'In progress',
    'fulbright-2026': 'Not started'
  });

  // System States & Sandbox demo controls
  const [demoEmptyState, setDemoEmptyState] = useState<boolean>(false);
  const [systemStateOverlay, setSystemStateOverlay] = useState<string | null>(null);
  const [sandboxOpen, setSandboxOpen] = useState<boolean>(false);
  const [showUploadFailedToast, setShowUploadFailedToast] = useState<boolean>(false);

  // Toggle Save Opportunity
  const handleToggleSave = (oppId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setSavedOpportunityIds(prev => 
      prev.includes(oppId) ? prev.filter(id => id !== oppId) : [...prev, oppId]
    );
  };

  // Update Application Progress in Saved Table
  const handleUpdateApplicationStatus = (oppId: string, status: ApplicationProgress) => {
    setApplicationStatuses(prev => ({
      ...prev,
      [oppId]: status
    }));
  };

  // Remove Saved
  const handleRemoveSaved = (oppId: string) => {
    setSavedOpportunityIds(prev => prev.filter(id => id !== oppId));
  };

  // Select Opportunity Detail
  const handleSelectOpportunity = (oppId: string) => {
    setSelectedOpportunityId(oppId);
  };

  // Return from Opportunity Detail to list
  const handleBackToDiscover = () => {
    setSelectedOpportunityId(null);
    setCurrentTab('discover');
  };

  // Selected Opportunity Object
  const selectedOpportunity = opportunities.find(opp => opp.id === selectedOpportunityId);
  const savedOpportunitiesList = opportunities.filter(opp => savedOpportunityIds.includes(opp.id));

  return (
    <div className="min-h-screen bg-[#F9FAFB] text-ink font-sans flex flex-col justify-between selection:bg-accent/15 selection:text-accent">
      
      <div>
        {/* Persistent Top Navigation Bar */}
        <Navbar
          currentTab={currentTab}
          onTabChange={(tab) => {
            setSelectedOpportunityId(null);
            setCurrentTab(tab);
          }}
          student={student}
          savedCount={savedOpportunityIds.length}
          onOpenSandbox={() => setSandboxOpen(!sandboxOpen)}
          sandboxOpen={sandboxOpen}
        />

        {/* Global Upload Failed Alert Toast (If triggered in demo) */}
        {showUploadFailedToast && (
          <div className="max-w-4xl mx-auto px-4 pt-4">
            <UploadFailedState
              fileName="corrupted_transcript.dat"
              errorMessage="Unsupported format — try another file. Supported: PDF, DOCX · Max 10MB."
              onDismiss={() => setShowUploadFailedToast(false)}
            />
          </div>
        )}

        {/* Main Content Router */}
        <main className="w-full">
          {/* SCREEN 4: Opportunity Detail (Key Screen) */}
          {selectedOpportunity ? (
            <OpportunityDetail
              opportunity={selectedOpportunity}
              student={student}
              isSaved={savedOpportunityIds.includes(selectedOpportunity.id)}
              onToggleSave={handleToggleSave}
              onBack={handleBackToDiscover}
              onSelectAlternativeOpportunity={handleSelectOpportunity}
              allOpportunities={opportunities}
            />
          ) : (
            <>
              {/* SCREEN 1: Document Upload */}
              {currentTab === 'onboarding-upload' && (
                <DocumentUpload
                  student={student}
                  onContinue={() => setCurrentTab('onboarding-review')}
                  onSkip={() => setCurrentTab('discover')}
                  onUploadFailedDemo={() => setShowUploadFailedToast(true)}
                />
              )}

              {/* SCREEN 2: Extraction Confirmation */}
              {currentTab === 'onboarding-review' && (
                <ExtractionReview
                  student={student}
                  onUpdateStudent={setStudent}
                  onConfirmAndContinue={() => setCurrentTab('discover')}
                  onReupload={() => setCurrentTab('onboarding-upload')}
                />
              )}

              {/* SCREEN 3: Dashboard */}
              {currentTab === 'discover' && (
                <DashboardView
                  opportunities={opportunities}
                  student={student}
                  savedOpportunityIds={savedOpportunityIds}
                  onToggleSave={handleToggleSave}
                  onSelectOpportunity={handleSelectOpportunity}
                  onGoToProfile={() => setCurrentTab('profile')}
                  onGoToOnboarding={() => setCurrentTab('onboarding-upload')}
                  demoEmptyState={demoEmptyState}
                />
              )}

              {/* SCREEN 5: Saved Opportunities */}
              {currentTab === 'saved' && (
                <SavedView
                  savedOpportunities={savedOpportunitiesList}
                  student={student}
                  applicationStatuses={applicationStatuses}
                  onUpdateApplicationStatus={handleUpdateApplicationStatus}
                  onRemoveSaved={handleRemoveSaved}
                  onSelectOpportunity={handleSelectOpportunity}
                  onBrowseOpportunities={() => setCurrentTab('discover')}
                />
              )}

              {/* SCREEN 6: Profile */}
              {currentTab === 'profile' && (
                <ProfileView
                  student={student}
                  onUpdateStudent={setStudent}
                />
              )}

              {/* SCREEN 7: Landing Page */}
              {currentTab === 'landing' && (
                <LandingPage
                  onStartOnboarding={() => setCurrentTab('onboarding-upload')}
                  onExploreCatalog={() => setCurrentTab('discover')}
                />
              )}

              {/* Applications tab placeholder / redirect to Saved table */}
              {currentTab === 'applications' && (
                <SavedView
                  savedOpportunities={savedOpportunitiesList}
                  student={student}
                  applicationStatuses={applicationStatuses}
                  onUpdateApplicationStatus={handleUpdateApplicationStatus}
                  onRemoveSaved={handleRemoveSaved}
                  onSelectOpportunity={handleSelectOpportunity}
                  onBrowseOpportunities={() => setCurrentTab('discover')}
                />
              )}
            </>
          )}
        </main>
      </div>

      {/* SYSTEM STATES OVERLAY MODAL (When inspecting Loading / Error / Upload states) */}
      {systemStateOverlay && (
        <div className="fixed inset-0 z-50 bg-ink/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="max-w-lg w-full relative">
            <button
              onClick={() => setSystemStateOverlay(null)}
              className="absolute -top-10 right-0 text-white hover:text-gray-200 text-xs font-semibold flex items-center gap-1"
            >
              <span>Close preview</span>
              <X className="w-4 h-4" />
            </button>
            {systemStateOverlay === 'loading' && (
              <LoadingState
                message="Analyzing opportunities... usually takes a few seconds"
                submessage="Comparing Alex Mengistu's GPA (3.82) & IELTS (7.5) against official sponsor criteria..."
              />
            )}
            {systemStateOverlay === 'error' && (
              <ErrorState
                title="Something went wrong"
                description="Our verification engine encountered a temporary sync timeout while pulling latest sponsor bylaws. Try again."
                onRetry={() => setSystemStateOverlay(null)}
              />
            )}
            {systemStateOverlay === 'upload_failed' && (
              <div className="bg-white p-6 rounded-2xl shadow-floating">
                <UploadFailedState
                  fileName="corrupted_transcript.xyz"
                  errorMessage="Unsupported format — try another file. Supported: PDF, DOCX · Max 10MB."
                  onDismiss={() => setSystemStateOverlay(null)}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Demo Floating Sandbox & Screen Switcher */}
      <StateSandbox
        isOpen={sandboxOpen}
        onClose={() => setSandboxOpen(false)}
        currentTab={currentTab}
        onTabChange={(tab) => {
          setSelectedOpportunityId(null);
          setCurrentTab(tab);
        }}
        onSelectOpportunity={handleSelectOpportunity}
        demoEmptyState={demoEmptyState}
        onToggleDemoEmptyState={() => setDemoEmptyState(!demoEmptyState)}
        systemStateOverlay={systemStateOverlay}
        onSetSystemStateOverlay={setSystemStateOverlay}
      />

      {/* Persistent Footer */}
      <footer className="border-t border-gray-100 bg-white py-6 mt-16 text-center text-xs text-grayText-600">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p>© 2026 Opportunity Hub. Verified deterministic matching for academic opportunities.</p>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setSandboxOpen(true)}
              className="text-accent hover:underline font-semibold"
            >
              Open Demo State Tester
            </button>
            <span>·</span>
            <button
              onClick={() => { setSelectedOpportunityId(null); setCurrentTab('landing'); }}
              className="hover:text-ink transition-colors"
            >
              Landing Page
            </button>
            <span>·</span>
            <button
              onClick={() => { setSelectedOpportunityId(null); setCurrentTab('discover'); }}
              className="hover:text-ink transition-colors"
            >
              Discover
            </button>
          </div>
        </div>
      </footer>

    </div>
  );
};

export default App;
