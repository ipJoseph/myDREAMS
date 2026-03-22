/**
 * TypeScript types for myDREAMS public API data.
 */

export interface Listing {
  id: string;
  mls_number: string;
  mls_source: string;
  mls_display_name?: string;
  status: string;
  list_price: number;
  original_list_price?: number;
  list_date?: string;
  days_on_market?: number;
  address: string;
  city: string;
  state: string;
  zip: string;
  county: string;
  latitude?: number;
  longitude?: number;
  elevation_feet?: number;
  subdivision?: string;
  property_type: string;
  property_subtype?: string;
  beds?: number;
  baths?: number;
  sqft?: number;
  acreage?: number;
  lot_sqft?: number;
  year_built?: number;
  stories?: number;
  garage_spaces?: number;
  heating?: string;
  cooling?: string;
  appliances?: string;
  interior_features?: string;
  exterior_features?: string;
  amenities?: string;
  views?: string;
  style?: string;
  roof?: string;
  sewer?: string;
  water_source?: string;
  construction_materials?: string;
  foundation?: string;
  flooring?: string;
  fireplace_features?: string;
  parking_features?: string;
  hoa_fee?: number;
  hoa_frequency?: string;
  tax_annual_amount?: number;
  tax_assessed_value?: number;
  listing_agent_name?: string;
  listing_agent_phone?: string;
  listing_agent_email?: string;
  listing_office_name?: string;
  primary_photo?: string;
  photos?: string[];
  photo_count?: number;
  virtual_tour_url?: string;
  public_remarks?: string;
  directions?: string;
  parcel_number?: string;
  sold_price?: number;
  sold_date?: string;
  updated_at?: string;
  also_listed_on?: AlsoListedOn[];
}

export interface AlsoListedOn {
  id: string;
  mls_number: string;
  mls_source: string;
  mls_display_name?: string;
  list_price: number;
  updated_at?: string;
}

export interface MapListing {
  id: string;
  mls_number: string;
  status: string;
  list_price: number;
  address: string;
  city: string;
  county: string;
  latitude: number;
  longitude: number;
  elevation_feet?: number;
  property_type: string;
  beds?: number;
  baths?: number;
  sqft?: number;
  primary_photo?: string;
}

export interface ListingSearchParams {
  status?: string;
  city?: string;
  county?: string;
  min_price?: number;
  max_price?: number;
  min_beds?: number;
  min_baths?: number;
  min_sqft?: number;
  min_acreage?: number;
  max_dom?: number;
  property_type?: string;
  mls_source?: string;
  q?: string;
  zone?: string;
  sort?: string;
  order?: "asc" | "desc";
  page?: number;
  limit?: number;
}

export interface Pagination {
  page: number;
  limit: number;
  total: number;
  pages: number;
}

export interface Area {
  name: string;
  listing_count: number;
  min_price: number;
  max_price: number;
  avg_price: number | null;
}

export interface AddressHistoryListing {
  id: string;
  mls_number: string;
  status: string;
  list_price: number;
  sold_price?: number;
  list_date?: string;
  sold_date?: string;
  days_on_market?: number;
  listing_office_name?: string;
}

export interface PropertyChange {
  change_type: string;
  old_value: string;
  new_value: string;
  change_amount?: number;
  change_percent?: number;
  date: string;
}

export interface AddressHistory {
  prior_listings: AddressHistoryListing[];
  changes: PropertyChange[];
}

export interface FeaturedCollection {
  id: string;
  name: string;
  description: string;
  slug: string;
  cover_image: string | null;
  featured_order: number | null;
  collection_type: string;
  created_at: string;
  property_count: number;
  min_price: number | null;
  max_price: number | null;
  avg_price: number | null;
}

export interface CollectionDetail {
  id: string;
  name: string;
  description: string;
  slug: string;
  cover_image: string | null;
  collection_type: string;
  created_at: string;
  listings: CollectionListing[];
  listing_count: number;
}

export interface CollectionListing {
  id: string;
  mls_number: string;
  status: string;
  list_price: number;
  sold_price?: number;
  address: string;
  city: string;
  state: string;
  zip: string;
  county: string;
  latitude?: number;
  longitude?: number;
  property_type: string;
  beds?: number;
  baths?: number;
  sqft?: number;
  acreage?: number;
  elevation_feet?: number;
  primary_photo?: string;
  photo_count?: number;
  days_on_market?: number;
  list_date?: string;
  year_built?: number;
  stories?: number;
  public_remarks?: string;
  display_order: number;
  agent_notes?: string;
}

export interface ListingStats {
  total_listings: number;
  active_listings: number;
  pending_listings: number;
  min_price: number;
  max_price: number;
  avg_price: number | null;
  cities_served: number;
  counties_served: number;
  by_property_type: { type: string; count: number }[];
  by_mls_source: { source: string; count: number }[];
}
