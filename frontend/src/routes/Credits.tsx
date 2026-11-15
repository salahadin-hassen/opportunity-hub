import { Page } from "../components/layout/Page";
import { MarketingFooter, MarketingNav } from "../components/marketing/MarketingChrome";
import { PHOTOS } from "../lib/photos";

export function Credits() {
  return (
    <Page title="Photography credits">
      <MarketingNav />
      <main id="main" className="mx-auto max-w-[1000px] px-5 pb-10 pt-32 sm:px-8">
        <h1 className="display text-[52px] text-ink sm:text-[80px]">Photography credits</h1>
        <p className="mt-6 max-w-[60ch] text-[16px] text-ink-soft">
          Every photograph on Opportunity Hub comes from Wikimedia Commons under an open licence. Places are shown as places: none of these images
          depicts a partner, and no one pictured is an Opportunity Hub user.
        </p>
        <ul className="mt-12 grid grid-cols-1 gap-x-8 gap-y-10 sm:grid-cols-2">
          {Object.entries(PHOTOS).map(([key, photo]) => (
            <li key={key}>
              <div className="overflow-hidden rounded-plate bg-sand" style={{ aspectRatio: photo.ratio }}>
                <img src={photo.small} alt={photo.alt} loading="lazy" decoding="async" className="plate-img" />
              </div>
              <p className="mt-3 text-[15px] font-semibold text-ink">{photo.caption}</p>
              <p className="mt-1 text-[14px] text-ink-soft">
                {photo.author},{" "}
                <a className="link" href={photo.licenseUrl} target="_blank" rel="noreferrer">
                  {photo.license}
                </a>
                .{" "}
                <a className="link" href={photo.source} target="_blank" rel="noreferrer">
                  Original on Wikimedia Commons
                </a>
                . Cropped and resized.
              </p>
            </li>
          ))}
        </ul>
      </main>
      <MarketingFooter />
    </Page>
  );
}
