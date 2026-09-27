import React, { useState, useEffect } from 'react';
import { 
  UploadCloud, 
  FileText, 
  CheckCircle2, 
  Loader2, 
  Plus, 
  Sparkles, 
  ArrowRight, 
  ShieldCheck, 
  FileCheck,
  AlertCircle,
  HelpCircle
} from 'lucide-react';
import { StudentProfile } from '../../types/opportunity';

interface DocumentUploadProps {
  student: StudentProfile;
  onContinue: () => void;
  onSkip: () => void;
  onUploadFailedDemo?: () => void;
}

export const DocumentUpload: React.FC<DocumentUploadProps> = ({
  student,
  onContinue,
  onSkip,
  onUploadFailedDemo
}) => {
  // Extraction progress state (starts at 68% or can simulate live)
  const [transcriptProgress, setTranscriptProgress] = useState<number>(68);
  const [isExtracting, setIsExtracting] = useState<boolean>(true);
  const [cvUploaded, setCvUploaded] = useState<boolean>(true);
  const [extraDocs, setExtraDocs] = useState<{ name: string; type: string }[]>([
    { name: 'IELTS_Official_TRF_ScoreReport.pdf', type: 'Language Test Sheet' }
  ]);

  // Simulate progress bar advancing
  useEffect(() => {
    if (!isExtracting) return;
    const interval = setInterval(() => {
      setTranscriptProgress(prev => {
        if (prev >= 100) {
          setIsExtracting(false);
          return 100;
        }
        return prev + 4;
      });
    }, 450);
    return () => clearInterval(interval);
  }, [isExtracting]);

  const handleRestartExtraction = () => {
    setTranscriptProgress(12);
    setIsExtracting(true);
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 sm:py-12">
      {/* Step Header */}
      <div className="text-center max-w-2xl mx-auto mb-10">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-accent-soft text-accent text-xs font-semibold uppercase tracking-wider mb-3">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Automated Eligibility Ingestion</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight">
          Upload your academic credentials
        </h1>
        <p className="mt-2 text-sm sm:text-base text-grayText-600">
          Our verified matching engine parses hard requirements directly from official transcripts and CVs so you never waste hours applying to programs you don’t qualify for.
        </p>
      </div>

      {/* Two Main Drag-and-Drop Zones */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        
        {/* Zone 1: Academic Transcript (Analyzing / In-Progress State) */}
        <div className="flex flex-col rounded-2xl bg-white border-2 border-accent/30 shadow-card p-6 relative overflow-hidden transition-all hover:border-accent">
          {/* Top Label */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-accent-soft flex items-center justify-center text-accent">
                <FileText className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-ink">Academic Transcript</h3>
                <p className="text-[11px] text-grayText-600 font-mono">Official / Unofficial PDF</p>
              </div>
            </div>
            {transcriptProgress < 100 ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200 text-xs font-semibold">
                <Loader2 className="w-3 h-3 animate-spin text-amber-600" />
                <span>Analyzing</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold">
                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                <span>Ready for review</span>
              </span>
            )}
          </div>

          {/* Card Body: Analyzing State as specified */}
          <div className="border border-dashed border-accent/40 rounded-xl bg-accent-soft/30 p-5 flex flex-col items-center justify-center text-center my-auto min-h-[170px]">
            <div className="w-10 h-10 rounded-full bg-accent/10 flex items-center justify-center mb-3">
              {transcriptProgress < 100 ? (
                <Loader2 className="w-5 h-5 text-accent animate-spin" />
              ) : (
                <FileCheck className="w-5 h-5 text-emerald-600" />
              )}
            </div>

            <p className="text-xs font-semibold text-ink mb-1">
              {transcriptProgress < 100 ? 'Analyzing transcript...' : 'Transcript parsed successfully!'}
            </p>
            <p className="text-[11px] text-grayText-600 mb-3 font-mono">
              Jimma_Univ_Official_Academic_Transcript_2026.pdf (2.4 MB)
            </p>

            {/* Progress percentage bar as specified */}
            <div className="w-full max-w-xs space-y-1.5">
              <div className="flex justify-between text-[11px] font-mono">
                <span className="text-grayText-600 font-medium">Extracting grades & coursework</span>
                <span className="text-accent font-bold">{transcriptProgress}%</span>
              </div>
              <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-accent rounded-full transition-all duration-300 ease-out"
                  style={{ width: `${transcriptProgress}%` }}
                />
              </div>
            </div>

            {transcriptProgress === 100 && (
              <button
                onClick={handleRestartExtraction}
                className="mt-3 text-[11px] text-accent font-medium hover:underline"
              >
                Re-simulate extraction
              </button>
            )}
          </div>

          {/* PARSED CRITERIA callout under Transcript */}
          <div className="mt-5 pt-4 border-t border-gray-100">
            <div className="flex items-center gap-1.5 mb-2">
              <ShieldCheck className="w-3.5 h-3.5 text-accent" />
              <span className="text-[10px] font-bold uppercase tracking-wider text-ink font-mono">
                PARSED CRITERIA
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="px-2 py-0.5 rounded-md bg-gray-100 text-ink text-xs font-mono font-medium">
                GPA & Grading Scale
              </span>
              <span className="px-2 py-0.5 rounded-md bg-gray-100 text-ink text-xs font-mono font-medium">
                Degree Level
              </span>
              <span className="px-2 py-0.5 rounded-md bg-gray-100 text-ink text-xs font-mono font-medium">
                Field of Study
              </span>
              <span className="px-2 py-0.5 rounded-md bg-gray-100 text-ink text-xs font-mono font-medium">
                Coursework
              </span>
            </div>
          </div>
        </div>

        {/* Zone 2: Curriculum Vitae (CV) / Resume (Ready State) */}
        <div className="flex flex-col rounded-2xl bg-white border border-gray-200 shadow-card p-6 relative overflow-hidden transition-all hover:border-gray-300">
          {/* Top Label */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-surface-100 flex items-center justify-center text-ink">
                <FileText className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-ink">Curriculum Vitae (CV) / Resume</h3>
                <p className="text-[11px] text-grayText-600 font-mono">PDF, DOCX up to 10MB</p>
              </div>
            </div>
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold">
              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
              <span>Ready</span>
            </span>
          </div>

          {/* Card Body: Dropzone / Ready State */}
          <div 
            onClick={() => setCvUploaded(!cvUploaded)}
            className="border-2 border-dashed border-gray-200 hover:border-accent hover:bg-accent-soft/20 rounded-xl p-5 flex flex-col items-center justify-center text-center my-auto min-h-[170px] cursor-pointer transition-all group"
          >
            <div className="w-10 h-10 rounded-full bg-gray-100 group-hover:bg-accent-soft flex items-center justify-center mb-3 transition-colors">
              <UploadCloud className="w-5 h-5 text-grayText-600 group-hover:text-accent transition-colors" />
            </div>

            <p className="text-xs font-semibold text-ink group-hover:text-accent mb-1 transition-colors">
              Alex_Mengistu_CV_Aerospace_2026.pdf
            </p>
            <p className="text-[11px] text-grayText-600 font-mono">
              Drop file here or browse — Supported: PDF, DOCX · Max 10MB
            </p>
            <span className="mt-3 text-[11px] font-semibold text-accent inline-flex items-center gap-1">
              <span>Change file</span>
            </span>
          </div>

          {/* PARSED CRITERIA callout under CV */}
          <div className="mt-5 pt-4 border-t border-gray-100">
            <div className="flex items-center gap-1.5 mb-2">
              <ShieldCheck className="w-3.5 h-3.5 text-accent" />
              <span className="text-[10px] font-bold uppercase tracking-wider text-ink font-mono">
                PARSED CRITERIA
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="px-2 py-0.5 rounded-md bg-gray-100 text-ink text-xs font-mono font-medium">
                Tools & Frameworks
              </span>
              <span className="px-2 py-0.5 rounded-md bg-gray-100 text-ink text-xs font-mono font-medium">
                Work Timeline
              </span>
              <span className="px-2 py-0.5 rounded-md bg-gray-100 text-ink text-xs font-mono font-medium">
                Research Positions
              </span>
            </div>
          </div>
        </div>

      </div>

      {/* Optional Row: Extra Documents (Certifications, test sheets) */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-10 shadow-subtle">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-ink font-mono">
              Optional Supporting Credentials
            </h4>
            <p className="text-xs text-grayText-600 mt-0.5">
              Attach standardized test reports (GRE, IELTS, TOEFL) or leadership certificates for automatic matching bonus.
            </p>
          </div>
          <button
            onClick={() => {
              if (extraDocs.length < 2) {
                setExtraDocs([...extraDocs, { name: 'ETS_Official_GRE_Report_2026.pdf', type: 'GRE Test Score' }]);
              } else if (onUploadFailedDemo) {
                onUploadFailedDemo();
              }
            }}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-accent hover:text-accent-hover bg-accent-soft hover:bg-accent-soft/80 px-3 py-1.5 rounded-lg transition-colors shrink-0"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add credential</span>
          </button>
        </div>

        <div className="space-y-2">
          {extraDocs.map((doc, idx) => (
            <div key={idx} className="flex items-center justify-between p-2.5 rounded-lg bg-surface-50 border border-gray-100 text-xs">
              <div className="flex items-center gap-2">
                <FileCheck className="w-4 h-4 text-emerald-600" />
                <span className="font-medium text-ink">{doc.name}</span>
                <span className="px-1.5 py-0.5 rounded bg-gray-200 text-gray-700 text-[10px] font-mono">
                  {doc.type}
                </span>
              </div>
              <span className="text-emerald-700 font-mono text-[11px] font-medium">
                Verified (Band 7.5)
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Footer Navigation: Skip for now / Continue */}
      <div className="flex items-center justify-between pt-6 border-t border-gray-200">
        <button
          onClick={onSkip}
          className="text-sm font-medium text-grayText-600 hover:text-ink px-4 py-2 rounded-lg hover:bg-gray-100 transition-colors"
        >
          Skip for now
        </button>

        <button
          onClick={onContinue}
          className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-white text-sm font-semibold px-6 py-2.5 rounded-xl shadow-sm hover:shadow transition-all group"
        >
          <span>Continue to verification</span>
          <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
        </button>
      </div>
    </div>
  );
};
