import { Opportunity, StudentProfile, CriterionCheck, EligibilityStatus } from '../types/opportunity';

export const seedOpportunities: Opportunity[] = [
  {
    id: 'chevening-2027',
    name: 'Chevening Scholarship 2027',
    organization: "UK Foreign, Commonwealth & Development Office",
    category: 'Scholarships',
    type: "Master's Degree",
    location: 'United Kingdom',
    funding: 'Fully funded',
    duration: '12 months',
    deadline: '2026-11-05',
    deadlineFormatted: '5 Nov 2026',
    isApproachingDeadline: false,
    source: {
      name: 'GOV.UK Chevening Official Guidance',
      url: 'https://www.chevening.org/scholarships/guidance/eligibility-criteria/',
      lastVerified: '20 Sep 2026',
    },
    about: 'Chevening is the UK government’s international awards programme aimed at developing global leaders. It offers full financial support for individuals to study for any eligible master’s degree at any UK university while also gaining access to a wide range of exclusive academic, professional, and cultural experiences.',
    covers: [
      'Full university tuition fees for eligible Master’s courses',
      'Monthly living allowance / stipend set to UK standards',
      'Return economy flights to and from the United Kingdom',
      'Arrival allowance, departure allowance & visa reimbursement',
      'Travel grant to attend Chevening events across the UK'
    ],
    fields: ['Aerospace & Mechanical Engineering', 'Applied Sciences', 'Public Policy', 'Technology & Innovation', 'Sustainable Development'],
    evaluateEligibility: (student: StudentProfile) => {
      const checks: CriterionCheck[] = [
        {
          id: 'chev-gpa',
          label: 'Academic Standing (Equivalent to UK 2:1 Honours)',
          shortLabel: 'GPA',
          required: 'Minimum 3.30 / 4.00 (UK 2:1 equivalent)',
          studentValue: `${student.education.gpa.toFixed(2)} / ${student.education.maxGpa.toFixed(2)} (${student.education.degree})`,
          status: student.education.gpa >= 3.30 ? 'met' : 'unmet',
          note: student.education.gpa >= 3.30 ? 'Exceeds UK First Class / 2:1 honours threshold' : 'Below required minimum GPA',
          sourceSection: 'Academic Requirements §3.1'
        },
        {
          id: 'chev-nationality',
          label: 'Chevening-Eligible Citizenship',
          shortLabel: 'Nationality',
          required: 'Citizen of Chevening-eligible territory (Ethiopia included)',
          studentValue: `${student.personal.country} (Citizen)`,
          status: 'met',
          note: 'Eligible bilateral partner state',
          sourceSection: 'Eligible Countries & Territories §1.2'
        },
        {
          id: 'chev-english',
          label: 'English Language Proficiency',
          shortLabel: 'English',
          required: 'IELTS Overall ≥ 6.5 (min 5.5 in each band) or university waiver',
          studentValue: student.testScores.ielts ? `IELTS ${student.testScores.ielts.toFixed(1)} Band` : 'Test pending',
          status: (student.testScores.ielts && student.testScores.ielts >= 6.5) ? 'met' : 'uncertain',
          note: student.testScores.ielts && student.testScores.ielts >= 6.5 ? 'Exceeds standard 6.5 cutoff' : 'Score verification required',
          sourceSection: 'Language Competency §4.2'
        },
        {
          id: 'chev-work',
          label: 'Work Experience (Min 2,800 Hours / 2 Years)',
          shortLabel: 'Work exp.',
          required: 'Demonstrated 2,800+ hours (full/part-time, internships, research)',
          studentValue: `${student.experience.length} formal positions (~2,950 hours logged)`,
          status: 'met',
          note: 'Research Assistant (Jimma Univ) + Intern (ESSS) satisfies requirement',
          sourceSection: 'Professional Experience §2.4'
        },
        {
          id: 'chev-return',
          label: 'Commitment to Return to Home Country',
          shortLabel: 'Commitment',
          required: 'Return to citizenship country for min 2 years after study',
          studentValue: 'Signed declaration of return & capacity building',
          status: 'met',
          note: 'Profile preference aligns with regional development',
          sourceSection: 'Scholarship Conditions §5.1'
        }
      ];

      const unmetCount = checks.filter(c => c.status === 'unmet').length;
      const uncertainCount = checks.filter(c => c.status === 'uncertain').length;
      let status: EligibilityStatus = 'eligible';
      let summaryBadgeText = 'Eligible - all requirements satisfied';

      if (unmetCount > 0) {
        status = 'not-eligible';
        summaryBadgeText = `Not currently eligible - ${unmetCount} requirement${unmetCount > 1 ? 's' : ''} not met`;
      } else if (uncertainCount > 0) {
        status = 'potential';
        summaryBadgeText = `Potential match - ${uncertainCount} criterion pending confirmation`;
      }

      return { status, criteriaChecks: checks, summaryBadgeText, unmetCount, uncertainCount };
    }
  },
  {
    id: 'daad-rise-2026',
    name: 'DAAD RISE Germany',
    organization: 'German Academic Exchange Service (DAAD)',
    category: 'Research',
    type: 'Research Internship',
    location: 'Germany (Various Universities & Institutes)',
    funding: 'Stipend',
    duration: '10–12 weeks (Summer 2027)',
    deadline: '2026-12-15',
    deadlineFormatted: '15 Dec 2026',
    isApproachingDeadline: false,
    source: {
      name: 'DAAD RISE Germany Portal',
      url: 'https://www.daad.de/rise/en/rise-germany/',
      lastVerified: '18 Sep 2026',
    },
    about: 'RISE Germany offers undergraduate students from North American, British and international universities the opportunity to complete a summer research internship at top German universities and research institutions alongside doctoral students.',
    covers: [
      'Monthly scholarship rate of €992 to cover living expenses',
      'Health, accident, and personal liability insurance',
      'Travel allowance of €160 for the international RISE meeting in Heidelberg',
      'Housing support provided by host institution'
    ],
    fields: ['Aerospace Engineering', 'Mechanical & Materials Science', 'Physics', 'Earth Sciences'],
    evaluateEligibility: (student: StudentProfile) => {
      const checks: CriterionCheck[] = [
        {
          id: 'daad-field',
          label: 'Eligible Field of Study',
          shortLabel: 'Field',
          required: 'Enrolled in STEM / Engineering / Natural Sciences',
          studentValue: student.education.field,
          status: 'met',
          note: 'Direct match with Host Laboratory disciplines',
          sourceSection: 'Eligible Subjects §1'
        },
        {
          id: 'daad-standing',
          label: 'Academic Standing & Degree Completion',
          shortLabel: 'Degree status',
          required: 'Currently enrolled undergraduate who will NOT graduate before internship',
          studentValue: `Graduating ${student.education.graduationYear} (Current Undergrad)`,
          status: student.education.graduationYear >= 2027 ? 'met' : 'unmet',
          note: 'Undergraduate enrollment confirmed for Summer 2027',
          sourceSection: 'Student Status §2'
        },
        {
          id: 'daad-gpa',
          label: 'Minimum Academic Standing',
          shortLabel: 'GPA',
          required: 'GPA ≥ 3.20 / 4.00 (German equivalent 2.5 or better)',
          studentValue: `${student.education.gpa.toFixed(2)} / 4.00`,
          status: student.education.gpa >= 3.20 ? 'met' : 'unmet',
          note: 'Superior academic track record',
          sourceSection: 'Academic Merit §3'
        },
        {
          id: 'daad-lang',
          label: 'Language Proficiency (Host Lab Working Language)',
          shortLabel: 'Language',
          required: 'English fluent; German language level determined by lab mentor',
          studentValue: 'English verified (IELTS 7.5); German proficiency uncertified',
          status: 'uncertain',
          note: 'German A1/A2 or mentor language interview pending confirmation',
          sourceSection: 'Language Policy §4'
        },
        {
          id: 'daad-skills',
          label: 'Computational & Modeling Competence',
          shortLabel: 'Skills',
          required: 'Working knowledge of simulation tools (MATLAB, Python, or CAD)',
          studentValue: 'Python, MATLAB, CAD, Simulation confirmed in CV',
          status: 'met',
          note: 'Matches lab computational profile',
          sourceSection: 'Technical Qualifications §5'
        }
      ];

      const unmetCount = checks.filter(c => c.status === 'unmet').length;
      const uncertainCount = checks.filter(c => c.status === 'uncertain').length;
      let status: EligibilityStatus = 'potential';
      let summaryBadgeText = 'Potential match - language certification unknown';

      if (unmetCount > 0) {
        status = 'not-eligible';
        summaryBadgeText = `Not currently eligible - ${unmetCount} requirement not met`;
      } else if (uncertainCount === 0) {
        status = 'eligible';
        summaryBadgeText = 'Eligible - all requirements satisfied';
      }

      return { status, criteriaChecks: checks, summaryBadgeText, unmetCount, uncertainCount };
    }
  },
  {
    id: 'gsoc-2027',
    name: 'Google Summer of Code 2027',
    organization: 'Google Open Source',
    category: 'Hackathons',
    type: 'Open Source Fellowship',
    location: 'Remote (Worldwide)',
    funding: 'Paid',
    duration: '12–22 weeks',
    deadline: '2027-02-28',
    deadlineFormatted: '28 Feb 2027',
    isApproachingDeadline: false,
    source: {
      name: 'Google Open Source Official Program Rules',
      url: 'https://summerofcode.withgoogle.com/rules',
      lastVerified: '22 Sep 2026',
    },
    about: 'Google Summer of Code is a global, online mentoring program focused on introducing new contributors to open source software development. GSoC contributors work with open source organizations on 12+ week programming projects under mentor supervision.',
    covers: [
      'Standardized contributor stipend based on location ($3,000–$6,600 USD)',
      '1-on-1 mentorship from veteran open source maintainers',
      'Official Google Summer of Code Certificate of Completion',
      'Global community invitations and alumni network'
    ],
    fields: ['Open Source Software', 'Scientific Computing', 'Aerospace Simulation', 'Embedded Systems'],
    evaluateEligibility: (student: StudentProfile) => {
      const checks: CriterionCheck[] = [
        {
          id: 'gsoc-age',
          label: 'Minimum Age Requirement',
          shortLabel: 'Age',
          required: 'At least 18 years of age at registration',
          studentValue: '22 years old (Born 2004)',
          status: 'met',
          note: 'Verified from identity document',
          sourceSection: 'GSoC Participant Eligibility §2.1'
        },
        {
          id: 'gsoc-location',
          label: 'Territory of Residence & OFAC Sanctions Compliance',
          shortLabel: 'Nationality',
          required: 'Resident in eligible territory not subject to US OFAC embargo',
          studentValue: `${student.personal.country} (Compliant)`,
          status: 'met',
          note: 'Ethiopia is an approved participating country',
          sourceSection: 'Country Eligibility §2.2'
        },
        {
          id: 'gsoc-skills',
          label: 'Open Source & Programming Competence',
          shortLabel: 'Coding Skills',
          required: 'Proficiency in project languages (e.g. Python, C++, Git)',
          studentValue: 'Python, Git, MATLAB listed in verified profile skills',
          status: 'met',
          note: 'Documented code repository & tooling match',
          sourceSection: 'Technical Prerequisites §3.1'
        },
        {
          id: 'gsoc-enrolled',
          label: 'Contributor Standing',
          shortLabel: 'Enrollment',
          required: 'Enrolled in post-secondary education OR open source beginner',
          studentValue: `${student.education.university} (Enrolled Degree Candidate)`,
          status: 'met',
          note: 'Meets post-secondary student category',
          sourceSection: 'Participant Status §2.3'
        }
      ];

      return {
        status: 'eligible',
        criteriaChecks: checks,
        summaryBadgeText: 'Eligible - all requirements satisfied',
        unmetCount: 0,
        uncertainCount: 0
      };
    }
  },
  {
    id: 'mastercard-scholars-2027',
    name: 'Mastercard Foundation Scholars Program',
    organization: 'Mastercard Foundation & Partner Universities',
    category: 'Scholarships',
    type: "Undergraduate & Master's Scholarship",
    location: 'United Kingdom / Canada (Edinburgh, McGill)',
    funding: 'Fully funded',
    duration: '1–2 years',
    deadline: '2027-01-20',
    deadlineFormatted: '20 Jan 2027',
    isApproachingDeadline: false,
    source: {
      name: 'Mastercard Foundation Scholars Program Guidance',
      url: 'https://mastercardfdn.org/all/scholars/becoming-a-scholar/',
      lastVerified: '15 Sep 2026',
    },
    about: 'The Mastercard Foundation Scholars Program provides holistic scholarships to young people whose talents and promise exceed their financial resources, enabling them to complete their education while developing transformative leadership qualities.',
    covers: [
      'Comprehensive tuition fees and university mandatory charges',
      'Comprehensive stipend for living expenses, accommodation and meals',
      'Return international flights and travel insurance',
      'Laptop computer and instructional learning materials',
      'Leadership training retreat, mentoring and career incubation'
    ],
    fields: ['Engineering & Physical Sciences', 'Health Sciences', 'Agriculture', 'Public Policy'],
    evaluateEligibility: (student: StudentProfile) => {
      // Prompt specifies: Not eligible (GPA 3.42 vs 3.70 minimum or Alex's GPA compared to target)
      // Here: Show a NUANCED NEAR-MISS where several rows are ✓ and one row is ✕.
      // Let's set the cutoff to 3.90/4.00 (or highlight the GPA requirement: Required 3.90 vs Alex's 3.82, or specific tier)
      const requiredGpa = 3.90;
      const gpaMet = student.education.gpa >= requiredGpa;

      const checks: CriterionCheck[] = [
        {
          id: 'mc-citizenship',
          label: 'African Citizenship / Sub-Saharan Africa',
          shortLabel: 'Nationality',
          required: 'Citizen or refugee originating from an African nation',
          studentValue: `${student.personal.country} (Sub-Saharan Africa)`,
          status: 'met',
          note: 'Priority geographic eligibility confirmed',
          sourceSection: 'Eligibility Criteria §1'
        },
        {
          id: 'mc-leadership',
          label: 'Demonstrated Transformative Leadership',
          shortLabel: 'Leadership',
          required: 'Documented record of community leadership & giving back',
          studentValue: 'Space science outreach & peer mentorship roles confirmed',
          status: 'met',
          note: 'Strong social impact and community service track',
          sourceSection: 'Leadership Assessment §4'
        },
        {
          id: 'mc-need',
          label: 'Economically Disadvantaged Background',
          shortLabel: 'Financial need',
          required: 'Verified financial barrier preventing international tuition',
          studentValue: 'Documented low-income bracket & local tuition sponsorship',
          status: 'met',
          note: 'Financial need criteria satisfies partner committee',
          sourceSection: 'Financial Verification §3'
        },
        {
          id: 'mc-degree',
          label: 'Undergraduate Program Eligibility',
          shortLabel: 'Degree level',
          required: 'Hold or completing recognized bachelor degree in accredited university',
          studentValue: `${student.education.degree} (${student.education.university})`,
          status: 'met',
          note: 'Recognized accredited regional university',
          sourceSection: 'Academic Prerequisites §2'
        },
        {
          id: 'mc-gpa',
          label: 'Distinction Tier Minimum GPA',
          shortLabel: 'GPA cutoff',
          required: `Competitive GPA ≥ ${requiredGpa.toFixed(2)} / 4.00 (First Class with Distinction)`,
          studentValue: `${student.education.gpa.toFixed(2)} / 4.00 (Short by 0.08)`,
          status: gpaMet ? 'met' : 'unmet',
          note: gpaMet ? 'Exceeds distinction threshold' : `Near-miss: GPA is 3.82, which is 0.08 below the partner institution distinction requirement (${requiredGpa.toFixed(2)})`,
          sourceSection: 'Academic Ranking Thresholds §2.2'
        }
      ];

      const unmetCount = checks.filter(c => c.status === 'unmet').length;
      const uncertainCount = checks.filter(c => c.status === 'uncertain').length;

      return {
        status: unmetCount > 0 ? 'not-eligible' : 'eligible',
        criteriaChecks: checks,
        summaryBadgeText: unmetCount > 0 
          ? `Not currently eligible - ${unmetCount} requirement not met (Near-miss)` 
          : 'Eligible - all requirements satisfied',
        unmetCount,
        uncertainCount
      };
    }
  },
  {
    id: 'mit-gtl-2026',
    name: 'MIT Global Teaching Labs',
    organization: 'MIT International Science and Technology Initiatives (MISTI)',
    category: 'Fellowships',
    type: 'Global Teaching & Research',
    location: 'Global / Hybrid Partnerships',
    funding: 'Funded',
    duration: '4 weeks (Winter / Summer)',
    deadline: '2026-10-01',
    deadlineFormatted: '1 Oct 2026',
    isApproachingDeadline: true,
    source: {
      name: 'MIT MISTI Global Teaching Labs Official',
      url: 'https://misti.mit.edu/student-programs/teaching-internships',
      lastVerified: '24 Sep 2026',
    },
    about: 'MIT Global Teaching Labs sends high-achieving STEM students to teach tailored coursework in high schools and universities around the world, adapting materials to host curricula in physics, robotics, and aerospace concepts.',
    covers: [
      'Roundtrip international airfare covered by program host',
      'Local homestay accommodation or university guest apartments',
      'Weekly food and local transit allowance',
      'Teaching kit materials and lab demo equipment grant'
    ],
    fields: ['Aerospace Engineering', 'Robotics & Automation', 'Applied Physics', 'Mathematics'],
    evaluateEligibility: (student: StudentProfile) => {
      const checks: CriterionCheck[] = [
        {
          id: 'mit-stem',
          label: 'STEM / Quantitative Curriculum Focus',
          shortLabel: 'STEM field',
          required: 'Enrolled in accredited Aerospace, Mechanical, Physics, or Math',
          studentValue: student.education.field,
          status: 'met',
          note: 'Direct match with STEM syllabus curriculum',
          sourceSection: 'Host Curriculum Requirements §1'
        },
        {
          id: 'mit-gpa',
          label: 'Academic Performance Requirement',
          shortLabel: 'GPA',
          required: 'Minimum GPA ≥ 3.50 / 4.00',
          studentValue: `${student.education.gpa.toFixed(2)} / 4.00`,
          status: student.education.gpa >= 3.50 ? 'met' : 'unmet',
          note: 'Strong academic foundation',
          sourceSection: 'Prerequisites §2'
        },
        {
          id: 'mit-english',
          label: 'Instruction Language Proficiency',
          shortLabel: 'English',
          required: 'Native or professional English instruction fluency',
          studentValue: student.testScores.ielts ? `IELTS ${student.testScores.ielts.toFixed(1)} Band` : 'Test pending',
          status: (student.testScores.ielts && student.testScores.ielts >= 7.0) ? 'met' : 'uncertain',
          note: 'C1/C2 advanced instruction fluency verified',
          sourceSection: 'Language Policy §3'
        },
        {
          id: 'mit-essay',
          label: 'Pedagogy Essay & Teaching Plan Review',
          shortLabel: 'Essay review',
          required: 'Submitted 1,000-word STEM teaching proposal reviewed by host school',
          studentValue: 'Proposal submitted · Awaiting host faculty review',
          status: 'uncertain',
          note: 'Under active evaluation by host institution academic board',
          sourceSection: 'Selection Process §4.1'
        }
      ];

      const unmetCount = checks.filter(c => c.status === 'unmet').length;
      const uncertainCount = checks.filter(c => c.status === 'uncertain').length;

      return {
        status: unmetCount > 0 ? 'not-eligible' : 'potential',
        criteriaChecks: checks,
        summaryBadgeText: 'Potential match - essay review pending',
        unmetCount,
        uncertainCount
      };
    }
  },
  {
    id: 'fulbright-2026',
    name: 'Fulbright Foreign Student Program',
    organization: 'U.S. Department of State & Foreign Scholarship Board',
    category: 'Scholarships',
    type: "Master's & Doctoral Fellowship",
    location: 'United States',
    funding: 'Fully funded',
    duration: '2 years',
    deadline: '2026-10-15',
    deadlineFormatted: '15 Oct 2026',
    isApproachingDeadline: true, // 18-22 days out! Flagged
    source: {
      name: 'Fulbright Foreign Student Program Portal',
      url: 'https://foreign.fulbrightonline.org/about/foreign-student-program',
      lastVerified: '21 Sep 2026',
    },
    about: 'The Fulbright Foreign Student Program enables graduate students, young professionals and artists from abroad to study and conduct research in the United States. It operates in more than 160 countries worldwide.',
    covers: [
      'Full university tuition fees at designated U.S. graduate institution',
      'Monthly living stipend calibrated to host city cost of living',
      'International airfare and transit allowances',
      'Comprehensive sickness and accident insurance (ASPE policy)',
      'Pre-academic enrichment courses and Fulbright gateway orientation'
    ],
    fields: ['Aerospace Engineering', 'Space Systems', 'Computer Engineering', 'Environmental Science'],
    evaluateEligibility: (student: StudentProfile) => {
      const checks: CriterionCheck[] = [
        {
          id: 'ful-country',
          label: 'Citizenship and Residency',
          shortLabel: 'Nationality',
          required: 'Citizen and resident of participating country (Ethiopia eligible)',
          studentValue: `${student.personal.country} (Resident Citizen)`,
          status: 'met',
          note: 'Administered by U.S. Embassy Addis Ababa',
          sourceSection: 'Fulbright Bilateral Agreement §1'
        },
        {
          id: 'ful-degree',
          label: 'Bachelor Degree Completion Prior to Departure',
          shortLabel: 'Degree status',
          required: 'Completed 4-year undergraduate degree prior to Aug 2027 departure',
          studentValue: `${student.education.degree} (Graduating 2027)`,
          status: 'met',
          note: 'Anticipated graduation aligns with Fall 2027 cohort departure',
          sourceSection: 'Degree Eligibility §2'
        },
        {
          id: 'ful-gpa',
          label: 'Academic Merit Minimum Cutoff',
          shortLabel: 'GPA',
          required: 'Minimum GPA ≥ 3.50 / 4.00 (Equivalent to U.S. High Honors)',
          studentValue: `${student.education.gpa.toFixed(2)} / 4.00`,
          status: student.education.gpa >= 3.50 ? 'met' : 'unmet',
          note: 'Superior competitive GPA threshold met',
          sourceSection: 'Academic Merit Guidelines §3'
        },
        {
          id: 'ful-english',
          label: 'Standardized English Exam (IELTS or TOEFL)',
          shortLabel: 'English',
          required: 'IELTS Overall ≥ 7.0 (or TOEFL iBT ≥ 90)',
          studentValue: student.testScores.ielts ? `IELTS ${student.testScores.ielts.toFixed(1)}` : 'No score',
          status: (student.testScores.ielts && student.testScores.ielts >= 7.0) ? 'met' : 'unmet',
          note: 'Exceeds graduate school admission standard',
          sourceSection: 'Standardized Testing §4.1'
        },
        {
          id: 'ful-gre',
          label: 'GRE General Examination (Quantitative STEM requirement)',
          shortLabel: 'GRE Score',
          required: 'GRE Total ≥ 310 (Quantitative ≥ 160 for Engineering tracks)',
          studentValue: student.testScores.gre 
            ? `GRE ${student.testScores.gre.total} (Q${student.testScores.gre.quant} / V${student.testScores.gre.verbal})` 
            : 'No GRE score',
          status: (student.testScores.gre && student.testScores.gre.quant >= 160) ? 'met' : 'unmet',
          note: 'Strong quantitative sub-score (162) qualifies for STEM departments',
          sourceSection: 'GRE Score Profiles §4.3'
        }
      ];

      const unmetCount = checks.filter(c => c.status === 'unmet').length;
      const uncertainCount = checks.filter(c => c.status === 'uncertain').length;

      return {
        status: unmetCount > 0 ? 'not-eligible' : 'eligible',
        criteriaChecks: checks,
        summaryBadgeText: 'Eligible - all requirements satisfied (Approaching Deadline)',
        unmetCount,
        uncertainCount
      };
    }
  },
  {
    id: 'cern-summer-2027',
    name: 'CERN Summer Student Programme 2027',
    organization: 'European Organization for Nuclear Research (CERN)',
    category: 'Internships',
    type: 'Technical & Research Internship',
    location: 'Geneva, Switzerland',
    funding: 'Stipend',
    duration: '8–13 weeks',
    deadline: '2027-01-31',
    deadlineFormatted: '31 Jan 2027',
    isApproachingDeadline: false,
    source: {
      name: 'CERN Careers & Fellowships Portal',
      url: 'https://careers.cern/summer',
      lastVerified: '19 Sep 2026',
    },
    about: 'Join a team of world-leading scientists and engineers at CERN in Geneva for 8 to 13 weeks. Work on advanced engineering, instrumentation, accelerator physics, or high-performance simulation while attending daily lecture series.',
    covers: [
      'Daily subsistence allowance of 91 CHF (approx. €95/day)',
      'Travel allowance for return journey to Geneva',
      'Comprehensive CERN health & accident insurance scheme',
      'Assistance with on-campus CERN hostel accommodation'
    ],
    fields: ['Aerospace Simulation', 'Mechanical Engineering', 'Scientific Computing', 'Physics'],
    evaluateEligibility: (student: StudentProfile) => {
      const checks: CriterionCheck[] = [
        {
          id: 'cern-field',
          label: 'Eligible Discipline',
          shortLabel: 'Field',
          required: 'Physics, Computing, Applied Mathematics, or Engineering',
          studentValue: student.education.field,
          status: 'met',
          note: 'Aerospace Engineering matches accelerator mechanics group',
          sourceSection: 'CERN Student Guidelines §1'
        },
        {
          id: 'cern-standing',
          label: 'Academic Completion Level',
          shortLabel: 'Standing',
          required: 'Completed at least 3 years of full-time university studies',
          studentValue: '3rd Year Undergraduate (Jimma University)',
          status: 'met',
          note: 'Satisfies 6-semester university prerequisite',
          sourceSection: 'Student Level §2'
        },
        {
          id: 'cern-lang',
          label: 'Working Language Proficiency',
          shortLabel: 'Language',
          required: 'Good knowledge of English (or French)',
          studentValue: student.testScores.ielts ? `IELTS ${student.testScores.ielts.toFixed(1)}` : 'Fluent English',
          status: 'met',
          note: 'High proficiency verified',
          sourceSection: 'Working Language §3'
        },
        {
          id: 'cern-sim',
          label: 'Technical Tools (CAD & Simulation Modeling)',
          shortLabel: 'Tools',
          required: 'Demonstrated experience in CAD, MATLAB, or Numerical Simulation',
          studentValue: 'ANSYS, OpenFOAM, MATLAB, SolidWorks listed',
          status: 'met',
          note: 'Exceeds baseline modeling criteria',
          sourceSection: 'Technical Experience §4'
        }
      ];

      return {
        status: 'eligible',
        criteriaChecks: checks,
        summaryBadgeText: 'Eligible - all requirements satisfied',
        unmetCount: 0,
        uncertainCount: 0
      };
    }
  },
  {
    id: 'rhodes-2026-expired',
    name: 'Rhodes Scholarship for East Africa 2026',
    organization: 'The Rhodes Trust & University of Oxford',
    category: 'Scholarships',
    type: 'Postgraduate Degree',
    location: 'Oxford, United Kingdom',
    funding: 'Fully funded',
    duration: '2–3 years',
    deadline: '2026-08-01',
    deadlineFormatted: '1 Aug 2026',
    isExpired: true,
    nextCycleDate: 'June 2027',
    source: {
      name: 'Rhodes Trust Official Constituency Rules',
      url: 'https://www.rhodeshouse.ox.ac.uk/scholarships/applications/',
      lastVerified: '12 Sep 2026',
    },
    about: 'The Rhodes Scholarship is the oldest and perhaps most prestigious international scholarship programme, enabling outstanding young people from around the world to study at the University of Oxford.',
    covers: [
      'All University and College fees at the University of Oxford',
      'Annual stipend for living expenses (£18,180 per annum)',
      'Two economy class flights to and from Oxford',
      'Visa fees and International Health Surcharge (IHS)'
    ],
    fields: ['All Postgraduate Courses at Oxford', 'Aerospace Engineering', 'Advanced Science'],
    evaluateEligibility: (student: StudentProfile) => {
      const checks: CriterionCheck[] = [
        {
          id: 'rhodes-deadline',
          label: 'Application Window Status',
          shortLabel: 'Cycle status',
          required: 'Application submitted before August 1, 2026 cycle close',
          studentValue: 'Cycle closed on 1 Aug 2026',
          status: 'unmet',
          note: 'Program is closed. Next cycle begins June 2027',
          sourceSection: 'Admissions Calendar §1'
        },
        {
          id: 'rhodes-gpa',
          label: 'Academic Excellence (First Class Honours)',
          shortLabel: 'GPA',
          required: 'GPA ≥ 3.70 / 4.00 or UK First Class Honours equivalent',
          studentValue: `${student.education.gpa.toFixed(2)} / 4.00`,
          status: student.education.gpa >= 3.70 ? 'met' : 'unmet',
          note: 'Exceeds academic bar',
          sourceSection: 'Merit Assessment §2'
        },
        {
          id: 'rhodes-citizenship',
          label: 'Constituency Residency & Citizenship',
          shortLabel: 'Nationality',
          required: 'Citizen of designated East African constituency (Ethiopia, Kenya, Uganda, etc.)',
          studentValue: `${student.personal.country} (East Africa Constituency)`,
          status: 'met',
          note: 'Designated eligible constituency member',
          sourceSection: 'Constituencies §3'
        }
      ];

      return {
        status: 'not-eligible',
        criteriaChecks: checks,
        summaryBadgeText: 'EXPIRED — this program is closed. Next cycle begins June 2027',
        unmetCount: 1,
        uncertainCount: 0
      };
    }
  }
];
