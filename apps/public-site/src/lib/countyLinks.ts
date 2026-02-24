/**
 * County GIS and document link builder.
 *
 * Ported from apps/property-dashboard/app.py COUNTY_LINKS.
 * Builds URLs client-side from county name + parcel number.
 */

interface CountyDoc {
  label: string;
  url: string;
}

interface CountyConfig {
  gis: string | null;
  prc: { label: string; template: string } | null;
  docs: { label: string; template: string }[];
}

const COUNTY_LINKS: Record<string, CountyConfig> = {
  Jackson: {
    gis: "https://gis.jacksonnc.org/rpv/?find={parcel_dashed}",
    prc: {
      label: "Property Record Card",
      template: "https://gis.jacksonnc.org/PRC/PRC/{parcel}.pdf",
    },
    docs: [
      {
        label: "Property Report",
        template: "https://gis.jacksonnc.org/reports/{parcel_dashed}.html",
      },
    ],
  },
  Macon: {
    gis: "https://gis2.maconnc.org/lightmap/Maps/default.htm?pid={parcel}",
    prc: {
      label: "Property Record Card",
      template:
        "https://gis.maconnc.org/itspublic/AppraisalCard.aspx?id={parcel}",
    },
    docs: [
      {
        label: "Property Card (HTML)",
        template: "https://gis2.maconnc.org/propcards/{parcel}.1.html",
      },
      {
        label: "Reappraisal Notice",
        template: "https://gis.maconnc.org/reappraisalnotices/{parcel}.pdf",
      },
    ],
  },
  Buncombe: {
    gis: "https://gis.buncombecounty.org/buncomap/Default.aspx?PINN={parcel}",
    prc: {
      label: "Property Record Card",
      template: "https://prc-buncombe.spatialest.com/#/property/{parcel}",
    },
    docs: [
      {
        label: "Tax Detail",
        template: "https://tax.buncombenc.gov/parcel/details/{parcel}",
      },
      {
        label: "PIN History",
        template: "https://pinhistory.buncombenc.gov/?P={parcel}",
      },
    ],
  },
  Henderson: {
    gis: "https://gisweb.hendersoncountync.gov/gisweb?pin={parcel}",
    prc: {
      label: "Property Summary",
      template:
        "https://lrcpwa.ncptscloud.com/Henderson/PropertySummary.aspx?PIN={parcel}",
    },
    docs: [],
  },
  Haywood: {
    gis: "https://maps.haywoodcountync.gov/gisweb/default.htm?find={parcel}",
    prc: {
      label: "Appraisal Card",
      template:
        "https://taxes.haywoodcountync.gov/itspublic/appraisalcard.aspx?id={parcel}",
    },
    docs: [],
  },
  Swain: {
    gis: "https://maps.swaincountync.gov/gis/?find={parcel}",
    prc: {
      label: "Appraisal Card",
      template:
        "https://www.bttaxpayerportal.com/ITSPublicSW/AppraisalCard.aspx?id={parcel}",
    },
    docs: [],
  },
  Clay: {
    gis: null,
    prc: {
      label: "Appraisal Card",
      template:
        "https://bttaxpayerportal.com/ITSPublicCL/AppraisalCard.aspx?id={parcel}",
    },
    docs: [],
  },
  Cherokee: {
    gis: "https://maps.cherokeecounty-nc.gov/GISweb/GISviewer/",
    prc: null,
    docs: [],
  },
  Graham: {
    gis: "https://bttaxpayerportal.com/itspublicgr/RealEstate.aspx",
    prc: null,
    docs: [],
  },
};

function applyTemplate(template: string, parcel: string, parcelDashed: string): string {
  return template
    .replace(/\{parcel_dashed\}/g, encodeURIComponent(parcelDashed))
    .replace(/\{parcel\}/g, encodeURIComponent(parcel));
}

/**
 * Build county document links from a county name and parcel number.
 * Returns null if county or parcel is missing, or if the county has no config.
 */
export function getCountyLinks(
  county: string | undefined | null,
  parcel: string | undefined | null
): { gisUrl: string | null; docs: CountyDoc[] } | null {
  if (!county || !parcel) return null;

  // Strip " County" suffix if present
  const cleanCounty = county.replace(/\s+County$/i, "").trim();
  const config = COUNTY_LINKS[cleanCounty];
  if (!config) return null;

  // Jackson County PINs need dashes: 7554695441 -> 7554-69-5441
  let parcelDashed = parcel;
  if (cleanCounty === "Jackson" && /^\d{10}$/.test(parcel)) {
    parcelDashed = `${parcel.slice(0, 4)}-${parcel.slice(4, 6)}-${parcel.slice(6)}`;
  }

  const gisUrl = config.gis ? applyTemplate(config.gis, parcel, parcelDashed) : null;

  const docs: CountyDoc[] = [];
  if (config.prc) {
    docs.push({
      label: config.prc.label,
      url: applyTemplate(config.prc.template, parcel, parcelDashed),
    });
  }
  for (const doc of config.docs) {
    docs.push({
      label: doc.label,
      url: applyTemplate(doc.template, parcel, parcelDashed),
    });
  }

  return { gisUrl, docs };
}

/** List of counties that have any links configured. */
export const SUPPORTED_COUNTIES = Object.keys(COUNTY_LINKS);
