"""
Western NC ZIP Code to County Lookup
Covers the primary WNC mountain region for real estate
"""

# ZIP Code → County mapping for Western North Carolina
WNC_ZIP_COUNTY = {
    # Macon County
    "28734": "Macon",      # Franklin
    "28741": "Macon",      # Highlands
    "28763": "Macon",      # Otto
    "28781": "Macon",      # Scaly Mountain
    "28775": "Macon",      # Scaly Mountain (partial)
    "28744": "Macon",      # Highlands (partial)

    # Jackson County
    "28717": "Jackson",    # Cashiers
    "28723": "Jackson",    # Cullowhee
    "28725": "Jackson",    # Dillsboro
    "28736": "Jackson",    # Glenville
    "28747": "Jackson",    # Lake Toxaway (partial)
    "28774": "Jackson",    # Sapphire
    "28779": "Jackson",    # Sylva
    "28783": "Jackson",    # Qualla (also Cherokee land)
    "28788": "Jackson",    # Webster

    # Swain County
    "28713": "Swain",      # Bryson City
    "28733": "Swain",      # Fontana Dam

    # Cherokee County
    "28906": "Cherokee",   # Murphy
    "28901": "Cherokee",   # Andrews
    "28902": "Cherokee",   # Brasstown
    "28904": "Cherokee",   # Marble
    "28905": "Cherokee",   # Peachtree

    # Graham County
    "28771": "Graham",     # Robbinsville
    "28702": "Graham",     # Fontana Village

    # Clay County
    "28904": "Clay",       # Hayesville
    "28905": "Clay",       # Hayesville area
    "28909": "Clay",       # Warne

    # Haywood County
    "28707": "Haywood",    # Balsam
    "28716": "Haywood",    # Canton
    "28721": "Haywood",    # Clyde
    "28745": "Haywood",    # Lake Junaluska
    "28751": "Haywood",    # Maggie Valley
    "28785": "Haywood",    # Waynesville
    "28786": "Haywood",    # Waynesville

    # Buncombe County
    "28701": "Buncombe",   # Alexander
    "28704": "Buncombe",   # Arden
    "28715": "Buncombe",   # Black Mountain
    "28748": "Buncombe",   # Leicester
    "28778": "Buncombe",   # Swannanoa
    "28787": "Buncombe",   # Weaverville
    "28801": "Buncombe",   # Asheville
    "28802": "Buncombe",   # Asheville
    "28803": "Buncombe",   # Asheville
    "28804": "Buncombe",   # Asheville
    "28805": "Buncombe",   # Asheville
    "28806": "Buncombe",   # Asheville

    # Henderson County
    "28710": "Henderson",  # Bat Cave
    "28726": "Henderson",  # East Flat Rock
    "28729": "Henderson",  # Etowah
    "28731": "Henderson",  # Flat Rock
    "28732": "Henderson",  # Fletcher
    "28739": "Henderson",  # Hendersonville
    "28742": "Henderson",  # Horse Shoe
    "28759": "Henderson",  # Mills River
    "28790": "Henderson",  # Zirconia
    "28791": "Henderson",  # Hendersonville
    "28792": "Henderson",  # Hendersonville

    # Transylvania County
    "28712": "Transylvania",  # Brevard
    "28708": "Transylvania",  # Balsam Grove
    "28718": "Transylvania",  # Cedar Mountain
    "28766": "Transylvania",  # Penrose
    "28768": "Transylvania",  # Pisgah Forest
    "28772": "Transylvania",  # Rosman

    # Polk County
    "28722": "Polk",       # Columbus
    "28756": "Polk",       # Mill Spring
    "28773": "Polk",       # Saluda
    "28782": "Polk",       # Tryon

    # Rutherford County
    "28043": "Rutherford", # Forest City
    "28746": "Rutherford", # Lake Lure
    "28139": "Rutherford", # Spindale

    # McDowell County
    "28752": "McDowell",   # Marion
    "28761": "McDowell",   # Nebo
    "28762": "McDowell",   # Old Fort

    # Burke County
    "28655": "Burke",      # Morganton
    "28690": "Burke",      # Valdese

    # Yancey County
    "28714": "Yancey",     # Burnsville
    "28755": "Yancey",     # Micaville

    # Mitchell County
    "28705": "Mitchell",   # Bakersville
    "28777": "Mitchell",   # Spruce Pine

    # Avery County
    "28604": "Avery",      # Banner Elk
    "28622": "Avery",      # Elk Park
    "28646": "Avery",      # Linville
    "28657": "Avery",      # Newland

    # Watauga County
    "28607": "Watauga",    # Boone
    "28605": "Watauga",    # Blowing Rock
    "28679": "Watauga",    # Sugar Grove
    "28684": "Watauga",    # Todd
    "28692": "Watauga",    # Vilas
    "28608": "Watauga",    # Boone (ASU)

    # Ashe County
    "28615": "Ashe",       # Creston
    "28617": "Ashe",       # Crumpler
    "28640": "Ashe",       # Jefferson
    "28643": "Ashe",       # Lansing
    "28694": "Ashe",       # West Jefferson
    "28626": "Ashe",       # Fleetwood
    "28618": "Ashe",       # Deep Gap

    # Alleghany County
    "28621": "Alleghany",  # Ennice
    "28675": "Alleghany",  # Sparta

    # Wilkes County
    "28659": "Wilkes",     # North Wilkesboro
    "28697": "Wilkes",     # Wilkesboro

    # Madison County
    "28743": "Madison",    # Hot Springs
    "28748": "Madison",    # Leicester (shared)
    "28753": "Madison",    # Marshall
    "28754": "Madison",    # Mars Hill
    "28787": "Madison",    # Weaverville (partial)

    # Whittier area (can be Jackson or Swain)
    "28789": "Jackson",    # Whittier (primarily Jackson)
}


def get_county(zip_code: str) -> str:
    """
    Get county name from ZIP code.
    Returns 'Unknown' if ZIP not in lookup.
    """
    # Clean the ZIP code
    zip_clean = str(zip_code).strip()[:5]
    return WNC_ZIP_COUNTY.get(zip_clean, "Unknown")


def get_all_zips_for_county(county: str) -> list:
    """Get all ZIP codes for a given county."""
    return [z for z, c in WNC_ZIP_COUNTY.items() if c.lower() == county.lower()]


if __name__ == "__main__":
    # Test
    test_zips = ["28734", "28741", "28779", "28713", "28906", "99999"]
    for z in test_zips:
        print(f"{z} → {get_county(z)}")
