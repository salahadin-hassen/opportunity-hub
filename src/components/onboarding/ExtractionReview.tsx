import React, { useState } from 'react';
import { 
  Check, 
  Edit3, 
  FileCheck2, 
  ArrowLeft, 
  ArrowRight, 
  Building2, 
  GraduationCap, 
  Award, 
  Calendar, 
  BookOpen, 
  X,
  Sparkles,
  Info
} from 'lucide-react';
import { StudentProfile } from '../../types/opportunity';

interface ExtractionReviewProps {
  student: StudentProfile;
  onUpdateStudent: (updated: StudentProfile) => void;
  onConfirmAndContinue: () => void;
  onReupload: () => void;
}

export const ExtractionReview: React.FC<ExtractionReviewProps> = ({
  student,
  onUpdateStudent,
  onConfirmAndContinue,
  onReupload
}) => {
  // Editing state for any row
  const [editingField, setEditingField] = useState<string | null>(null);

  // Local form state
  const [university, setUniversity] = useState(student.education.university);
  const [degree, setDegree] = useState(student.education.degree);
  const [gpa, setGpa] = useState(student.education.gpa.toString());
  const [graduationYear, setGraduationYear] = useState(student.education.graduationYear.toString());
  const [coursesInput, setCoursesInput] = useState(student.education.relevantCourses.join(', '));

  const handleSaveField = (fieldName: string) => {
    const updated = { ...student };
    if (fieldName === 'university') {
      updated.education.university = university;
    } else if (fieldName === 'degree') {
      updated.education.degree = degree;
    } else if (fieldName === 'gpa') {
      const parsedGpa = parseFloat(gpa);
      if (!isNaN(parsedGpa) && parsedGpa > 0 && parsedGpa <= 4.0) {
        updated.education.gpa = parsedGpa;
      }
    } else if (fieldName === 'graduationYear') {
      const parsedYear = parseInt(graduationYear, 10);
      if (!isNaN(parsedYear)) {
        updated.education.graduationYear = parsedYear;
      }
    } else if (fieldName === 'courses') {
      updated.education.relevantCourses = coursesInput
        .split(',')
        .map(c => c.trim())
        .filter(c => c.length > 0);
    }
    onUpdateStudent(updated);
    setEditingField(null);
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 sm:py-12">
      {/* Header */}
      <div className="mb-8">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-800 text-xs font-semibold uppercase tracking-wider mb-3 border border-emerald-200">
          <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
          <span>Extraction Complete · 99.4% Confidence</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold text-ink tracking-tight">
          Review extracted information
        </h1>
        <p className="mt-2 text-sm sm:text-base text-grayText-600">
          We found the following from your transcript. Edit anything that looks incorrect so our deterministic match rules reflect your exact qualifications.
        </p>
      </div>

      {/* Main Review Card */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-card divide-y divide-gray-100 overflow-hidden mb-8">
        
        {/* Row 1: University */}
        <div className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-surface-50/50 transition-colors">
          <div className="flex items-start gap-3.5 flex-1">
            <div className="w-9 h-9 rounded-lg bg-surface-100 flex items-center justify-center text-ink shrink-0 mt-0.5">
              <Building2 className="w-4 h-4 text-grayText-600" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-semibold text-grayText-600 uppercase tracking-wider">
                  University
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent-soft text-accent text-[10px] font-medium font-mono">
                  Extracted from transcript
                </span>
              </div>
              {editingField === 'university' ? (
                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="text"
                    value={university}
                    onChange={e => setUniversity(e.target.value)}
                    className="flex-1 px-3 py-1.5 text-sm border border-accent rounded-lg focus:outline-none ring-2 ring-accent/20"
                    autoFocus
                  />
                  <button
                    onClick={() => handleSaveField('university')}
                    className="p-1.5 bg-accent text-white rounded-lg hover:bg-accent-hover"
                  >
                    <Check className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setEditingField(null)}
                    className="p-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <p className="text-sm sm:text-base font-semibold text-ink">
                  {student.education.university}
                </p>
              )}
            </div>
          </div>
          {editingField !== 'university' && (
            <button
              onClick={() => setEditingField('university')}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-grayText-600 hover:text-accent px-2.5 py-1.5 rounded-lg hover:bg-gray-100 transition-colors shrink-0 self-start sm:self-center"
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Edit</span>
            </button>
          )}
        </div>

        {/* Row 2: Degree */}
        <div className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-surface-50/50 transition-colors">
          <div className="flex items-start gap-3.5 flex-1">
            <div className="w-9 h-9 rounded-lg bg-surface-100 flex items-center justify-center text-ink shrink-0 mt-0.5">
              <GraduationCap className="w-4 h-4 text-grayText-600" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-semibold text-grayText-600 uppercase tracking-wider">
                  Degree & Major
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent-soft text-accent text-[10px] font-medium font-mono">
                  Extracted from transcript
                </span>
              </div>
              {editingField === 'degree' ? (
                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="text"
                    value={degree}
                    onChange={e => setDegree(e.target.value)}
                    className="flex-1 px-3 py-1.5 text-sm border border-accent rounded-lg focus:outline-none ring-2 ring-accent/20"
                    autoFocus
                  />
                  <button
                    onClick={() => handleSaveField('degree')}
                    className="p-1.5 bg-accent text-white rounded-lg hover:bg-accent-hover"
                  >
                    <Check className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setEditingField(null)}
                    className="p-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <p className="text-sm sm:text-base font-semibold text-ink">
                  {student.education.degree}
                </p>
              )}
            </div>
          </div>
          {editingField !== 'degree' && (
            <button
              onClick={() => setEditingField('degree')}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-grayText-600 hover:text-accent px-2.5 py-1.5 rounded-lg hover:bg-gray-100 transition-colors shrink-0 self-start sm:self-center"
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Edit</span>
            </button>
          )}
        </div>

        {/* Row 3: GPA */}
        <div className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-surface-50/50 transition-colors">
          <div className="flex items-start gap-3.5 flex-1">
            <div className="w-9 h-9 rounded-lg bg-surface-100 flex items-center justify-center text-ink shrink-0 mt-0.5">
              <Award className="w-4 h-4 text-emerald-600" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-semibold text-grayText-600 uppercase tracking-wider">
                  Cumulative GPA
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent-soft text-accent text-[10px] font-medium font-mono">
                  Extracted from transcript
                </span>
              </div>
              {editingField === 'gpa' ? (
                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="number"
                    step="0.01"
                    min="1.0"
                    max="4.0"
                    value={gpa}
                    onChange={e => setGpa(e.target.value)}
                    className="w-32 px-3 py-1.5 text-sm border border-accent rounded-lg font-mono focus:outline-none ring-2 ring-accent/20"
                    autoFocus
                  />
                  <span className="text-xs text-grayText-600 font-mono">/ 4.00</span>
                  <button
                    onClick={() => handleSaveField('gpa')}
                    className="p-1.5 bg-accent text-white rounded-lg hover:bg-accent-hover"
                  >
                    <Check className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setEditingField(null)}
                    className="p-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <div className="flex items-baseline gap-2">
                  <span className="text-lg font-bold text-ink font-mono">
                    {student.education.gpa.toFixed(2)}
                  </span>
                  <span className="text-xs font-mono text-grayText-600">/ 4.00 scale (Top 5% Cohort)</span>
                </div>
              )}
            </div>
          </div>
          {editingField !== 'gpa' && (
            <button
              onClick={() => setEditingField('gpa')}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-grayText-600 hover:text-accent px-2.5 py-1.5 rounded-lg hover:bg-gray-100 transition-colors shrink-0 self-start sm:self-center"
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Edit</span>
            </button>
          )}
        </div>

        {/* Row 4: Graduation */}
        <div className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-surface-50/50 transition-colors">
          <div className="flex items-start gap-3.5 flex-1">
            <div className="w-9 h-9 rounded-lg bg-surface-100 flex items-center justify-center text-ink shrink-0 mt-0.5">
              <Calendar className="w-4 h-4 text-grayText-600" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-semibold text-grayText-600 uppercase tracking-wider">
                  Anticipated Graduation
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent-soft text-accent text-[10px] font-medium font-mono">
                  Extracted from transcript
                </span>
              </div>
              {editingField === 'graduationYear' ? (
                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="number"
                    value={graduationYear}
                    onChange={e => setGraduationYear(e.target.value)}
                    className="w-32 px-3 py-1.5 text-sm border border-accent rounded-lg font-mono focus:outline-none ring-2 ring-accent/20"
                    autoFocus
                  />
                  <button
                    onClick={() => handleSaveField('graduationYear')}
                    className="p-1.5 bg-accent text-white rounded-lg hover:bg-accent-hover"
                  >
                    <Check className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setEditingField(null)}
                    className="p-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <p className="text-sm sm:text-base font-semibold text-ink font-mono">
                  {student.education.graduationYear} (Senior Standing)
                </p>
              )}
            </div>
          </div>
          {editingField !== 'graduationYear' && (
            <button
              onClick={() => setEditingField('graduationYear')}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-grayText-600 hover:text-accent px-2.5 py-1.5 rounded-lg hover:bg-gray-100 transition-colors shrink-0 self-start sm:self-center"
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Edit</span>
            </button>
          )}
        </div>

        {/* Row 5: Relevant courses */}
        <div className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-start justify-between gap-3 hover:bg-surface-50/50 transition-colors">
          <div className="flex items-start gap-3.5 flex-1">
            <div className="w-9 h-9 rounded-lg bg-surface-100 flex items-center justify-center text-ink shrink-0 mt-0.5">
              <BookOpen className="w-4 h-4 text-grayText-600" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-semibold text-grayText-600 uppercase tracking-wider">
                  Relevant Courses ({student.education.relevantCourses.length})
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent-soft text-accent text-[10px] font-medium font-mono">
                  Extracted from transcript
                </span>
              </div>
              {editingField === 'courses' ? (
                <div className="space-y-2 mt-2">
                  <textarea
                    rows={3}
                    value={coursesInput}
                    onChange={e => setCoursesInput(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-accent rounded-lg focus:outline-none ring-2 ring-accent/20"
                    placeholder="Comma-separated courses"
                  />
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleSaveField('courses')}
                      className="px-3 py-1 bg-accent text-white text-xs font-semibold rounded-lg hover:bg-accent-hover"
                    >
                      Save Courses
                    </button>
                    <button
                      onClick={() => setEditingField(null)}
                      className="px-3 py-1 bg-gray-100 text-gray-700 text-xs font-semibold rounded-lg hover:bg-gray-200"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {student.education.relevantCourses.map((course, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-1 rounded-md bg-surface-100 text-ink text-xs font-medium border border-gray-200"
                    >
                      {course}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
          {editingField !== 'courses' && (
            <button
              onClick={() => setEditingField('courses')}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-grayText-600 hover:text-accent px-2.5 py-1.5 rounded-lg hover:bg-gray-100 transition-colors shrink-0 self-start"
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Edit</span>
            </button>
          )}
        </div>

      </div>

      {/* Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-2">
        <button
          onClick={onReupload}
          className="inline-flex items-center gap-2 text-sm font-medium text-grayText-600 hover:text-ink px-4 py-2.5 rounded-xl border border-gray-200 hover:bg-gray-50 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Re-upload document</span>
        </button>

        <button
          onClick={onConfirmAndContinue}
          className="inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white text-sm font-semibold px-6 py-2.5 rounded-xl shadow-sm hover:shadow transition-all group"
        >
          <span>Confirm and continue</span>
          <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
        </button>
      </div>

      {/* Footer note as specified */}
      <div className="flex items-center justify-center gap-1.5 mt-6 text-xs text-grayText-600 text-center">
        <Info className="w-3.5 h-3.5 text-grayText-400" />
        <span>You can always update this later from your profile.</span>
      </div>
    </div>
  );
};
