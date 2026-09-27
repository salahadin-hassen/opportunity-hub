import React, { useState } from 'react';
import { 
  User, 
  GraduationCap, 
  Award, 
  Sparkles, 
  Briefcase, 
  FileText, 
  Sliders, 
  Edit3, 
  Plus, 
  Check, 
  X, 
  Eye, 
  RefreshCw,
  Calendar,
  MapPin,
  Mail,
  ShieldCheck
} from 'lucide-react';
import { StudentProfile, WorkPosition } from '../../types/opportunity';

interface ProfileViewProps {
  student: StudentProfile;
  onUpdateStudent: (updated: StudentProfile) => void;
}

export const ProfileView: React.FC<ProfileViewProps> = ({
  student,
  onUpdateStudent
}) => {
  // Section edit modal / inline toggles
  const [activeEditSection, setActiveEditSection] = useState<string | null>(null);

  // Form states
  const [personalForm, setPersonalForm] = useState(student.personal);
  const [educationForm, setEducationForm] = useState(student.education);
  const [testForm, setTestForm] = useState(student.testScores);
  const [skillsForm, setSkillsForm] = useState<string[]>(student.skills);
  const [newSkillInput, setNewSkillInput] = useState('');
  
  // Experience modal/add form
  const [isAddingExp, setIsAddingExp] = useState(false);
  const [newExpTitle, setNewExpTitle] = useState('');
  const [newExpOrg, setNewExpOrg] = useState('');
  const [newExpDates, setNewExpDates] = useState('');

  // Completeness calculation
  const completeness = 88; // 88% complete

  const handleSavePersonal = () => {
    onUpdateStudent({
      ...student,
      personal: personalForm
    });
    setActiveEditSection(null);
  };

  const handleSaveEducation = () => {
    onUpdateStudent({
      ...student,
      education: educationForm
    });
    setActiveEditSection(null);
  };

  const handleSaveTests = () => {
    onUpdateStudent({
      ...student,
      testScores: testForm
    });
    setActiveEditSection(null);
  };

  const handleAddSkill = () => {
    if (newSkillInput.trim() && !skillsForm.includes(newSkillInput.trim())) {
      const updatedSkills = [...skillsForm, newSkillInput.trim()];
      setSkillsForm(updatedSkills);
      onUpdateStudent({
        ...student,
        skills: updatedSkills
      });
      setNewSkillInput('');
    }
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    const updatedSkills = skillsForm.filter(s => s !== skillToRemove);
    setSkillsForm(updatedSkills);
    onUpdateStudent({
      ...student,
      skills: updatedSkills
    });
  };

  const handleAddExperience = () => {
    if (!newExpTitle.trim() || !newExpOrg.trim()) return;
    const newPos: WorkPosition = {
      id: `exp-${Date.now()}`,
      title: newExpTitle,
      organization: newExpOrg,
      startDate: newExpDates.split('–')[0]?.trim() || '2025',
      endDate: newExpDates.split('–')[1]?.trim() || 'Present',
    };
    onUpdateStudent({
      ...student,
      experience: [newPos, ...student.experience]
    });
    setIsAddingExp(false);
    setNewExpTitle('');
    setNewExpOrg('');
    setNewExpDates('');
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12 min-h-screen">
      
      {/* Profile Header & Completeness Meter */}
      <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6 sm:p-8 mb-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-6 border-b border-gray-100">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-accent text-white flex items-center justify-center font-bold text-2xl shadow-sm">
              AM
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl sm:text-2xl font-bold text-ink">{student.personal.name}</h1>
                <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold">
                  Verified Student
                </span>
              </div>
              <p className="text-xs sm:text-sm text-grayText-600 mt-0.5">
                {student.education.university} · {student.education.degree}
              </p>
            </div>
          </div>

          <div className="text-left md:text-right">
            <span className="text-xs text-grayText-600 font-mono block">Primary Field of Research</span>
            <span className="text-sm font-bold text-ink">{student.education.field}</span>
          </div>
        </div>

        {/* Completeness Meter: "NN% complete · Add [x] to improve matching" */}
        <div className="pt-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2 text-xs sm:text-sm">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-accent" />
              <span className="font-bold text-ink font-mono">{completeness}% complete</span>
              <span className="text-grayText-400">·</span>
              <span className="text-grayText-600">
                Add <strong>German language certificate or Statement of Purpose</strong> to reach 100% eligibility accuracy.
              </span>
            </div>
            <span className="text-accent font-semibold font-mono text-xs">High Matching Accuracy</span>
          </div>

          <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-accent to-emerald-500 rounded-full transition-all duration-500 ease-out" 
              style={{ width: `${completeness}%` }}
            />
          </div>
        </div>
      </div>

      <div className="space-y-6">
        
        {/* Section 1: Personal Information */}
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6 sm:p-7">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-surface-100 flex items-center justify-center text-ink">
                <User className="w-4 h-4" />
              </div>
              <h3 className="text-base font-bold text-ink">Personal information</h3>
            </div>
            {activeEditSection !== 'personal' ? (
              <button
                onClick={() => setActiveEditSection('personal')}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-grayText-600 hover:text-accent px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <Edit3 className="w-3.5 h-3.5" />
                <span>Edit</span>
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSavePersonal}
                  className="inline-flex items-center gap-1 text-xs font-semibold bg-accent text-white px-3 py-1.5 rounded-lg hover:bg-accent-hover"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>Save</span>
                </button>
                <button
                  onClick={() => setActiveEditSection(null)}
                  className="p-1.5 text-grayText-600 hover:bg-gray-100 rounded-lg"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>

          {activeEditSection === 'personal' ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-grayText-600 block mb-1">Full Name</label>
                <input
                  type="text"
                  value={personalForm.name}
                  onChange={e => setPersonalForm({ ...personalForm, name: e.target.value })}
                  className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-grayText-600 block mb-1">Country of Citizenship</label>
                <input
                  type="text"
                  value={personalForm.country}
                  onChange={e => setPersonalForm({ ...personalForm, country: e.target.value })}
                  className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-grayText-600 block mb-1">City</label>
                <input
                  type="text"
                  value={personalForm.city}
                  onChange={e => setPersonalForm({ ...personalForm, city: e.target.value })}
                  className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-grayText-600 block mb-1">Date of Birth</label>
                <input
                  type="date"
                  value={personalForm.dateOfBirth}
                  onChange={e => setPersonalForm({ ...personalForm, dateOfBirth: e.target.value })}
                  className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:border-accent focus:outline-none"
                />
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
              <div>
                <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold">Full Name</span>
                <span className="font-semibold text-ink text-sm">{student.personal.name}</span>
              </div>
              <div>
                <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold">Citizenship</span>
                <span className="font-semibold text-ink text-sm">{student.personal.country}</span>
              </div>
              <div>
                <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold">City</span>
                <span className="font-semibold text-ink text-sm">{student.personal.city}</span>
              </div>
              <div>
                <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold">Date of Birth</span>
                <span className="font-semibold text-ink text-sm font-mono">{student.personal.dateOfBirth}</span>
              </div>
            </div>
          )}
        </div>

        {/* Section 2: Education */}
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6 sm:p-7">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-surface-100 flex items-center justify-center text-ink">
                <GraduationCap className="w-4 h-4" />
              </div>
              <h3 className="text-base font-bold text-ink">Education & Coursework</h3>
            </div>
            {activeEditSection !== 'education' ? (
              <button
                onClick={() => setActiveEditSection('education')}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-grayText-600 hover:text-accent px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <Edit3 className="w-3.5 h-3.5" />
                <span>Edit</span>
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSaveEducation}
                  className="inline-flex items-center gap-1 text-xs font-semibold bg-accent text-white px-3 py-1.5 rounded-lg hover:bg-accent-hover"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>Save</span>
                </button>
                <button
                  onClick={() => setActiveEditSection(null)}
                  className="p-1.5 text-grayText-600 hover:bg-gray-100 rounded-lg"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>

          {activeEditSection === 'education' ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-grayText-600 block mb-1">University</label>
                <input
                  type="text"
                  value={educationForm.university}
                  onChange={e => setEducationForm({ ...educationForm, university: e.target.value })}
                  className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-grayText-600 block mb-1">Degree & Major</label>
                <input
                  type="text"
                  value={educationForm.degree}
                  onChange={e => setEducationForm({ ...educationForm, degree: e.target.value })}
                  className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-grayText-600 block mb-1">GPA (out of 4.00)</label>
                <input
                  type="number"
                  step="0.01"
                  value={educationForm.gpa}
                  onChange={e => setEducationForm({ ...educationForm, gpa: parseFloat(e.target.value) || 0 })}
                  className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg font-mono focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-grayText-600 block mb-1">Graduation Year</label>
                <input
                  type="number"
                  value={educationForm.graduationYear}
                  onChange={e => setEducationForm({ ...educationForm, graduationYear: parseInt(e.target.value, 10) || 2027 })}
                  className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg font-mono focus:border-accent focus:outline-none"
                />
              </div>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs mb-4">
                <div>
                  <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold">University</span>
                  <span className="font-semibold text-ink text-sm">{student.education.university}</span>
                </div>
                <div>
                  <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold">Degree</span>
                  <span className="font-semibold text-ink text-sm">{student.education.degree}</span>
                </div>
                <div>
                  <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold">Cumulative GPA</span>
                  <span className="font-bold text-accent text-sm font-mono">{student.education.gpa.toFixed(2)} / 4.00</span>
                </div>
                <div>
                  <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold">Graduation</span>
                  <span className="font-semibold text-ink text-sm font-mono">{student.education.graduationYear}</span>
                </div>
              </div>

              <div>
                <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold mb-2">Verified Coursework</span>
                <div className="flex flex-wrap gap-1.5">
                  {student.education.relevantCourses.map((c, i) => (
                    <span key={i} className="px-2 py-0.5 rounded bg-surface-100 text-ink text-xs font-medium border border-gray-200">
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Section 3: Test Scores */}
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6 sm:p-7">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-surface-100 flex items-center justify-center text-ink">
                <Award className="w-4 h-4" />
              </div>
              <h3 className="text-base font-bold text-ink">Standardized Test Scores</h3>
            </div>
            {activeEditSection !== 'tests' ? (
              <button
                onClick={() => setActiveEditSection('tests')}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-grayText-600 hover:text-accent px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <Edit3 className="w-3.5 h-3.5" />
                <span>Edit</span>
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSaveTests}
                  className="inline-flex items-center gap-1 text-xs font-semibold bg-accent text-white px-3 py-1.5 rounded-lg hover:bg-accent-hover"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>Save</span>
                </button>
                <button
                  onClick={() => setActiveEditSection(null)}
                  className="p-1.5 text-grayText-600 hover:bg-gray-100 rounded-lg"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* IELTS Card */}
            <div className="p-4 rounded-2xl bg-surface-50 border border-gray-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-ink">IELTS Academic</span>
                <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 text-[10px] font-bold font-mono">
                  Verified
                </span>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-extrabold text-ink font-mono">{student.testScores.ielts}</span>
                <span className="text-xs text-grayText-600 font-mono">/ 9.0 Band (C1 Competency)</span>
              </div>
            </div>

            {/* GRE Card */}
            <div className="p-4 rounded-2xl bg-surface-50 border border-gray-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-ink">GRE General</span>
                <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 text-[10px] font-bold font-mono">
                  Verified
                </span>
              </div>
              <div className="flex items-baseline gap-2 mb-2">
                <span className="text-2xl font-extrabold text-ink font-mono">{student.testScores.gre?.total}</span>
                <span className="text-xs text-grayText-600 font-mono">/ 340 Total</span>
              </div>
              <div className="flex items-center gap-3 text-xs font-mono text-grayText-600 pt-2 border-t border-gray-200">
                <span>V: <strong className="text-ink">{student.testScores.gre?.verbal}</strong></span>
                <span>Q: <strong className="text-ink">{student.testScores.gre?.quant}</strong></span>
                <span>AW: <strong className="text-ink">{student.testScores.gre?.analyticalWriting}</strong></span>
              </div>
            </div>
          </div>
        </div>

        {/* Section 4: Skills */}
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6 sm:p-7">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-base font-bold text-ink">Skills & Frameworks</h3>
            <span className="text-xs text-grayText-600 font-mono">{student.skills.length} skills</span>
          </div>

          <div className="flex flex-wrap gap-2 mb-4">
            {student.skills.map((skill, i) => (
              <span 
                key={i} 
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-accent-soft text-accent text-xs font-semibold"
              >
                <span>{skill}</span>
                <button 
                  onClick={() => handleRemoveSkill(skill)}
                  className="hover:text-accent-hover"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>

          <div className="flex items-center gap-2 max-w-sm">
            <input
              type="text"
              value={newSkillInput}
              onChange={e => setNewSkillInput(e.target.value)}
              placeholder="Add skill (e.g. C++, ROS)..."
              className="flex-1 px-3 py-1.5 text-xs border border-gray-200 rounded-lg focus:border-accent focus:outline-none"
              onKeyDown={e => e.key === 'Enter' && handleAddSkill()}
            />
            <button
              onClick={handleAddSkill}
              className="px-3 py-1.5 bg-accent text-white text-xs font-semibold rounded-lg hover:bg-accent-hover transition-colors"
            >
              Add
            </button>
          </div>
        </div>

        {/* Section 5: Experience */}
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6 sm:p-7">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-surface-100 flex items-center justify-center text-ink">
                <Briefcase className="w-4 h-4" />
              </div>
              <h3 className="text-base font-bold text-ink">Positions & Experience</h3>
            </div>
            <button
              onClick={() => setIsAddingExp(true)}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-accent hover:text-accent-hover bg-accent-soft px-3 py-1.5 rounded-lg transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add experience</span>
            </button>
          </div>

          {isAddingExp && (
            <div className="p-4 rounded-2xl bg-surface-50 border border-gray-200 mb-4 space-y-3 text-xs">
              <h4 className="font-bold text-ink">New Position</h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <input
                  type="text"
                  placeholder="Title (e.g. Lab Intern)"
                  value={newExpTitle}
                  onChange={e => setNewExpTitle(e.target.value)}
                  className="px-3 py-1.5 border border-gray-200 rounded-lg"
                />
                <input
                  type="text"
                  placeholder="Organization"
                  value={newExpOrg}
                  onChange={e => setNewExpOrg(e.target.value)}
                  className="px-3 py-1.5 border border-gray-200 rounded-lg"
                />
                <input
                  type="text"
                  placeholder="Dates (e.g. Jan 2025–Present)"
                  value={newExpDates}
                  onChange={e => setNewExpDates(e.target.value)}
                  className="px-3 py-1.5 border border-gray-200 rounded-lg"
                />
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleAddExperience}
                  className="px-3 py-1 bg-accent text-white rounded-lg font-semibold"
                >
                  Save
                </button>
                <button
                  onClick={() => setIsAddingExp(false)}
                  className="px-3 py-1 bg-gray-100 text-gray-700 rounded-lg font-semibold"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          <div className="space-y-3">
            {student.experience.map(pos => (
              <div key={pos.id} className="p-4 rounded-2xl bg-surface-50 border border-gray-100 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h4 className="font-bold text-ink text-sm">{pos.title}</h4>
                  <p className="text-grayText-600 font-medium">{pos.organization}</p>
                  {pos.description && (
                    <p className="text-gray-500 mt-1 text-[11px]">{pos.description}</p>
                  )}
                </div>
                <span className="font-mono text-grayText-600 text-xs shrink-0">
                  {pos.startDate} – {pos.endDate}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Section 6: Documents */}
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6 sm:p-7">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-surface-100 flex items-center justify-center text-ink">
                <FileText className="w-4 h-4" />
              </div>
              <h3 className="text-base font-bold text-ink">Uploaded Documents</h3>
            </div>
          </div>

          <div className="space-y-3">
            {student.documents.map(doc => (
              <div key={doc.id} className="p-3.5 rounded-2xl bg-surface-50 border border-gray-100 flex items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-accent-soft flex items-center justify-center text-accent">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="font-bold text-ink">{doc.name}</p>
                    <p className="text-grayText-600 font-mono text-[11px]">{doc.size} · Uploaded {doc.uploadedAt}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button 
                    onClick={() => alert(`Viewing ${doc.name}`)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-gray-200 text-grayText-600 hover:text-ink text-xs font-semibold hover:bg-white transition-colors"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>View</span>
                  </button>
                  <button 
                    onClick={() => alert(`Replace file dialog opened for ${doc.name}`)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-gray-200 text-grayText-600 hover:text-ink text-xs font-semibold hover:bg-white transition-colors"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>Replace</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Section 7: Preferences */}
        <div className="bg-white rounded-3xl border border-gray-200 shadow-card p-6 sm:p-7">
          <div className="flex items-center gap-2.5 mb-4">
            <div className="w-8 h-8 rounded-lg bg-surface-100 flex items-center justify-center text-ink">
              <Sliders className="w-4 h-4" />
            </div>
            <h3 className="text-base font-bold text-ink">Matching Preferences</h3>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
            <div>
              <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold">Target Regions</span>
              <span className="font-semibold text-ink">{student.preferences.preferredLocations.join(', ')}</span>
            </div>
            <div>
              <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold">Funding Preference</span>
              <span className="font-semibold text-ink">{student.preferences.fundingPreference}</span>
            </div>
            <div>
              <span className="text-grayText-400 block font-mono uppercase text-[10px] font-bold">Earliest Availability</span>
              <span className="font-semibold text-ink font-mono">{student.preferences.availableFrom}</span>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};
