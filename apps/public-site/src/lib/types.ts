/**
 * TypeScript types for myDREAMS public API data.
 */

export interface Listing {
  id: string;
  mls_number: string;
  mls_source: string;
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
