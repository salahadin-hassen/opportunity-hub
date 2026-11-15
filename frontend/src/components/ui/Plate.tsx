import { motion, useReducedMotion } from "motion/react";
import { PHOTOS, type PhotoKey } from "../../lib/photos";

/**
 * A photograph treated as an atlas plate: fixed aspect ratio (no layout shift),
 * responsive WebP sources, and a caption that carries its credit and licence.
 * `reveal` wipes the image in once, the first time it enters the viewport.
 */
export function Plate({
  photo,
  number,
  className = "",
  imgClassName = "",
  ratio,
  sizes = "(min-width: 1024px) 60vw, 100vw",
  priority = false,
  reveal = true,
  caption = "below",
  objectPosition,
}: {
  photo: PhotoKey;
  number?: string;
  className?: string;
  imgClassName?: string;
  /** Override the crop (width / height); defaults to the photo's own ratio. */
  ratio?: number;
  sizes?: string;
  priority?: boolean;
  reveal?: boolean;
  caption?: "below" | "overlay" | "none";
  objectPosition?: string;
}) {
  const image = PHOTOS[photo];
  const reduced = useReducedMotion();
  const animate = reveal && !reduced;
  return (
    <figure className={className}>
      <motion.div
        className="relative overflow-hidden rounded-plate bg-sand"
        style={{ aspectRatio: ratio ?? image.ratio }}
        initial={animate ? "hidden" : false}
        whileInView={animate ? "shown" : undefined}
        viewport={{ once: true, amount: 0.2 }}
      >
        {/* The image is never clipped itself, so lazy loading and in-view detection work; an ivory cover wipes away instead. */}
        <motion.img
          src={image.small}
          srcSet={`${image.small} 800w, ${image.large} 1600w`}
          sizes={sizes}
          alt={image.alt}
          loading={priority ? "eager" : "lazy"}
          decoding="async"
          fetchPriority={priority ? "high" : "auto"}
          className={`plate-img ${imgClassName}`}
          style={{ objectPosition }}
          variants={{ hidden: { scale: 1.1 }, shown: { scale: 1 } }}
          transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1] }}
        />
        {animate && (
          <motion.span
            aria-hidden="true"
            className="absolute inset-0 origin-top bg-ivory"
            variants={{ hidden: { scaleY: 1 }, shown: { scaleY: 0 } }}
            transition={{ duration: 1, ease: [0.65, 0, 0.35, 1] }}
          />
        )}
        {caption === "overlay" && (
          <figcaption className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-4 bg-gradient-to-t from-night/70 to-transparent px-4 pb-3 pt-10 text-[12px] text-snow/90">
            <span>
              {number && <span className="num mr-2 text-lime">{number}</span>}
              {image.caption}
            </span>
            <Credit photo={photo} tone="paper" />
          </figcaption>
        )}
      </motion.div>
      {caption === "below" && (
        <figcaption className="mt-2.5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-[12.5px] text-muted">
          <span>
            {number && <span className="num mr-2 text-ink">{number}</span>}
            {image.caption}
          </span>
          <Credit photo={photo} />
        </figcaption>
      )}
    </figure>
  );
}

export function Credit({ photo, tone = "muted" }: { photo: PhotoKey; tone?: "muted" | "paper" }) {
  const image = PHOTOS[photo];
  return (
    <span className={tone === "paper" ? "text-snow/75" : "text-faint"}>
      Photo{" "}
      <a href={image.source} target="_blank" rel="noreferrer" className="underline decoration-1 underline-offset-2 hover:text-current">
        {image.author}
      </a>
      ,{" "}
      <a href={image.licenseUrl} target="_blank" rel="noreferrer" className="underline decoration-1 underline-offset-2">
        {image.license}
      </a>
    </span>
  );
}
