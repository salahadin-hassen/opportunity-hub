import { StudentProfile } from '../types/opportunity';

export const seedStudent: StudentProfile = {
  personal: {
    name: 'Alex Mengistu',
    country: 'Ethiopia',
    city: 'Jimma',
    dateOfBirth: '2004-03-14',
    email: 'alex.mengistu@ju.edu.et',
  },
  education: {
    university: 'Jimma University',
    degree: 'BSc Aerospace Engineering',
    gpa: 3.82,
    maxGpa: 4.00,
    graduationYear: 2027,
    field: 'Aerospace Engineering',
    relevantCourses: [
      'Aerodynamics & Fluid Dynamics',
      'Flight Mechanics & Control',
      'Orbital Mechanics',
      'Propulsion Systems',
      'Computational Fluid Dynamics (CFD)',
      'Engineering Thermodynamics',
      'Structural Analysis for Aerospace'
    ],
  },
  testScores: {
    ielts: 7.5,
    gre: {
      total: 320,
      verbal: 158,
      quant: 162,
      analyticalWriting: 4.0,
    },
  },
  skills: [
    'Python',
    'MATLAB',
    'CAD (SolidWorks)',
    'Simulation (ANSYS / OpenFOAM)',
    'Technical Writing',
    'Research Methods',
    'Git',
    'Data Analysis (NumPy/Pandas)'
  ],
  experience: [
    {
      id: 'exp-1',
      title: 'Research Assistant',
      organization: 'Jimma University Fluid Mechanics Lab',
      startDate: 'Jan 2025',
      endDate: 'Aug 2026',
      description: 'Conducted subsonic wind-tunnel analysis and aerodynamic drag profiling for modified UAV wingtips under Dr. K. Tadesse.'
    },
    {
      id: 'exp-2',
      title: 'Space Engineering Intern',
      organization: 'Ethiopian Space Science Society (ESSS)',
      startDate: 'Jun 2024',
      endDate: 'Sep 2024',
      description: 'Assisted telemetry instrumentation calibration and ground-station satellite tracking operations for low-Earth orbit CubeSats.'
    }
  ],
  documents: [
    {
      id: 'doc-transcript',
      name: 'Jimma_Univ_Official_Academic_Transcript_2026.pdf',
      type: 'transcript',
      size: '2.4 MB',
      uploadedAt: 'Today, 2:15 PM',
      status: 'analyzed'
    },
    {
      id: 'doc-cv',
      name: 'Alex_Mengistu_CV_Aerospace_2026.pdf',
      type: 'cv',
      size: '1.1 MB',
      uploadedAt: 'Today, 2:16 PM',
      status: 'analyzed'
    }
  ],
  preferences: {
    preferredLocations: ['United Kingdom', 'Germany', 'United States', 'Remote', 'Europe'],
    fundingPreference: 'Fully funded or high-stipend',
    availableFrom: 'Summer 2027'
  }
};
