/**
 * Editorial photography, self-hosted as responsive WebP (800w / 1600w).
 *
 * Every image comes from Wikimedia Commons under CC0, CC BY or CC BY-SA, so
 * each one is credited on the page that shows it and on /credits. None depicts
 * a partner institution or an Opportunity Hub user; places are named only as
 * places.
 */
import campusPath1600 from "../assets/photos/campus-path-1600.webp";
import campusPath800 from "../assets/photos/campus-path-800.webp";
import observatory1600 from "../assets/photos/observatory-1600.webp";
import observatory800 from "../assets/photos/observatory-800.webp";
import radioTelescope1600 from "../assets/photos/radio-telescope-1600.webp";
import radioTelescope800 from "../assets/photos/radio-telescope-800.webp";
import readingRoom1600 from "../assets/photos/reading-room-1600.webp";
import readingRoom800 from "../assets/photos/reading-room-800.webp";
import spiral1600 from "../assets/photos/spiral-1600.webp";
import spiral800 from "../assets/photos/spiral-800.webp";
import telescope1600 from "../assets/photos/telescope-1600.webp";
import telescope800 from "../assets/photos/telescope-800.webp";

export type Photo = {
  small: string;
  large: string;
  /** Intrinsic aspect ratio (width / height) so layout never shifts while loading. */
  ratio: number;
  alt: string;
  /** Short place caption, as an atlas plate would carry. */
  caption: string;
  author: string;
  license: string;
  licenseUrl: string;
  source: string;
};

export const PHOTOS = {
  telescope: {
    small: telescope800,
    large: telescope1600,
    ratio: 3840 / 3097,
    alt: "A brass coin-operated telescope on a high balcony, pointed out over the rooftops of Paris under a cloudy sky.",
    caption: "Looking out over Paris",
    author: "Dietmar Rabich",
    license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0",
    source: "https://commons.wikimedia.org/wiki/File:Paris,_Eiffelturm,_Teleskop_--_2014_--_1272.jpg",
  },
  campusPath: {
    small: campusPath800,
    large: campusPath1600,
    ratio: 2438 / 1835,
    alt: "Students walking along a long, tree-lined path through a green university campus.",
    caption: "Students on the move",
    author: "Duke Makangila",
    license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0",
    source: "https://commons.wikimedia.org/wiki/File:University_students_on_the_move.jpg",
  },
  observatory: {
    small: observatory800,
    large: observatory1600,
    ratio: 3840 / 2373,
    alt: "A domed observatory tower on a mountain plateau under the dense band of the Milky Way.",
    caption: "Assy-Turgen Observatory at night",
    author: "Astrobond",
    license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0",
    source:
      "https://commons.wikimedia.org/wiki/File:Assy-Turgen_Observatory_against_the_backdrop_of_the_center_of_the_Milky_Way_and_the_star-forming_region_around_Antares.jpg",
  },
  readingRoom: {
    small: readingRoom800,
    large: readingRoom1600,
    ratio: 3840 / 2550,
    alt: "A long reading room under iron arches, with rows of wooden desks, green lamps and readers at work.",
    caption: "Reading room, Bibliothèque Sainte-Geneviève",
    author: "Marie-Lan Nguyen",
    license: "CC BY 2.0 FR",
    licenseUrl: "https://creativecommons.org/licenses/by/2.0/fr/deed.en",
    source: "https://commons.wikimedia.org/wiki/File:Salle_de_lecture_Bibliotheque_Sainte-Genevieve_n03.jpg",
  },
  spiral: {
    small: spiral800,
    large: spiral1600,
    ratio: 3840 / 2562,
    alt: "Looking straight up a spiral staircase towards an octagonal glass skylight.",
    caption: "Spiral staircase, seen from below",
    author: "Wilfredor",
    license: "CC0 1.0",
    licenseUrl: "https://creativecommons.org/publicdomain/zero/1.0/deed.en",
    source: "https://commons.wikimedia.org/wiki/File:Spiral_staircase_in_the_Vatican_Museums_from_bottom_02.jpg",
  },
  radioTelescope: {
    small: radioTelescope800,
    large: radioTelescope1600,
    ratio: 3840 / 2560,
    alt: "A large white radio telescope dish tilted towards a blue sky with scattered clouds.",
    caption: "Sardinia Radio Telescope",
    author: "Mike Peel (www.mikepeel.net)",
    license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0",
    source: "https://commons.wikimedia.org/wiki/File:At_Sardinia_2025_010_-_Sardinia_Radio_Telescope.jpg",
  },
} satisfies Record<string, Photo>;

export type PhotoKey = keyof typeof PHOTOS;
