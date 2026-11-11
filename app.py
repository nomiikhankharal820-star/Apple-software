
import streamlit as st
import sqlite3
import requests
import pandas as pd
import time
from datetime import datetime
from urllib.parse import quote

# =====================================================
# 1. PAGE CONFIG
# =====================================================

st.set_page_config(
    page_title="City-to-City Lead Generator",
    page_icon="🌍",
    layout="wide"
)

DB_NAME = "software_house.db"

# =====================================================
# 2. DESIGN
# =====================================================

st.markdown("""
<style>
.stApp {
    background: #f4f7fb;
}
.block-container {
    padding-top: 1.5rem;
}
.hero {
    background: linear-gradient(120deg,#10233f,#2563eb);
    padding: 28px;
    border-radius: 16px;
    color: white;
    margin-bottom: 20px;
}
.hero h1 {
    color: white;
    font-size: 32px;
}
.hero p {
    color: #dbeafe;
}
.metric-card {
    background: white;
    padding: 18px;
    border-radius: 14px;
    border: 1px solid #e2e8f0;
}
.metric-card h2 {
    color: #2563eb;
    font-size: 30px;
}
.metric-card p {
    color: #64748b;
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# 3. DATABASE
# =====================================================

def db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def initialize_database():

    conn = db_connection()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS city_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        osm_ref TEXT NOT NULL,
        name TEXT,
        city TEXT,
        country TEXT,
        category TEXT,
        phone TEXT,
        email TEXT,
        website TEXT,
        address TEXT,
        latitude REAL,
        longitude REAL,
        score INTEGER DEFAULT 0,
        score_reason TEXT,
        status TEXT DEFAULT 'New',
        notes TEXT,
        created_at TEXT,
        updated_at TEXT,
        UNIQUE(osm_ref, city, country)
    )
    """)

    conn.commit()
    conn.close()


initialize_database()

# =====================================================
# 4. BUSINESS CATEGORIES
# =====================================================

CATEGORY_FILTERS = {
    "All Businesses": [
        '["name"]',
        '["shop"]',
        '["office"]',
        '["craft"]',
        '["amenity"]',
        '["healthcare"]',
        '["tourism"]',
        '["leisure"]',
        '["industrial"]'
    ],

    "Shops": [
        '["name"]["shop"]'
    ],

    "Offices": [
        '["name"]["office"]'
    ],

    "Food & Hospitality": [
        '["name"]["amenity"~"restaurant|cafe|fast_food|bar|pub|food_court"]',
        '["name"]["tourism"~"hotel|motel|guest_house|hostel"]'
    ],

    "Healthcare": [
        '["name"]["healthcare"]',
        '["name"]["amenity"~"hospital|clinic|doctors|dentist|pharmacy"]'
    ],

    "Education": [
        '["name"]["amenity"~"school|university|college|kindergarten"]'
    ],

    "Tourism": [
        '["name"]["tourism"]'
    ],

    "Other Services": [
        '["name"]["craft"]',
        '["name"]["leisure"]',
        '["name"]["industrial"]'
    ]
}

# =====================================================
# 5. GEOCODING
# =====================================================

def get_city_location(city, country):

    url = "https://nominatim.openstreetmap.org/search"

    headers = {
        "User-Agent": "CityToCityLeadGenerator/1.0 (business research app)"
    }

    params = {
        "city": city,
        "country": country,
        "format": "jsonv2",
        "limit": 1
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    results = response.json()

    if not results:
        raise Exception(
            f"Location not found: {city}, {country}"
        )

    return (
        float(results[0]["lat"]),
        float(results[0]["lon"])
    )

# =====================================================
# 6. OVERPASS BUSINESS SEARCH
# =====================================================

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter"
]


def search_city_businesses(
    city,
    country,
    latitude,
    longitude,
    radius,
    category,
    result_limit
):

    filters = CATEGORY_FILTERS[category]

    selectors = []

    for item in filters:

        selectors.append(
            f'nwr(around:{radius},{latitude},{longitude}){item};'
        )

    query = f"""
    [out:json][timeout:60];
    (
        {" ".join(selectors)}
    );
    out center tags {result_limit};
    """

    headers = {
        "User-Agent": "CityToCityLeadGenerator/1.0"
    }

    last_error = None

    for endpoint in OVERPASS_URLS:

        try:

            response = requests.post(
                endpoint,
                data={"data": query},
                headers=headers,
                timeout=90
            )

            response.raise_for_status()

            data = response.json()

            return data.get("elements", [])

        except Exception as error:

            last_error = error

    raise Exception(
        f"Overpass search failed: {last_error}"
    )

# =====================================================
# 7. EXTRACT BUSINESS INFORMATION
# =====================================================

def get_value(tags, *keys):

    for key in keys:

        value = tags.get(key)

        if value:
            return value

    return ""


def extract_business(element):

    tags = element.get("tags", {})

    name = tags.get("name", "")

    if not name:
        return None

    if element["type"] == "node":

        latitude = element.get("lat")
        longitude = element.get("lon")

    else:

        center = element.get("center", {})

        latitude = center.get("lat")
        longitude = center.get("lon")

    if latitude is None or longitude is None:
        return None

    category = "Other Business"

    for key in [
        "shop",
        "office",
        "amenity",
        "healthcare",
        "tourism",
        "craft",
        "leisure",
        "industrial"
    ]:

        if tags.get(key):

            category = (
                key.replace("_", " ").title()
                + ": "
                + str(tags[key]).replace("_", " ").title()
            )

            break

    phone = get_value(
        tags,
        "contact:phone",
        "phone"
    )

    email = get_value(
        tags,
        "contact:email",
        "email"
    )

    website = get_value(
        tags,
        "contact:website",
        "website"
    )

    street = get_value(
        tags,
        "addr:street"
    )

    house = get_value(
        tags,
        "addr:housenumber"
    )

    postcode = get_value(
        tags,
        "addr:postcode"
    )

    address_parts = [
        house,
        street,
        tags.get("addr:city", ""),
        postcode
    ]

    address = ", ".join(
        str(part) for part in address_parts if part
    )

    osm_ref = f'{element["type"]}/{element["id"]}'

    maps_url = (
        f"https://www.openstreetmap.org/"
        f"?mlat={latitude}&mlon={longitude}"
        f"#map=18/{latitude}/{longitude}"
    )

    return {
        "osm_ref": osm_ref,
        "name": name,
        "category": category,
        "phone": phone,
        "email": email,
        "website": website,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "maps_url": maps_url
    }

# =====================================================
# 8. LEAD SCORING
# =====================================================

def calculate_score(business):

    score = 40
    reasons = []

    if not business["website"]:

        score += 20
        reasons.append("No website listed")

    else:

        reasons.append("Website listed")

    if business["phone"]:

        score += 15
        reasons.append("Public phone available")

    if business["email"]:

        score += 15
        reasons.append("Public email available")

    score = min(score, 100)

    if score >= 75:
        temperature = "Hot"

    elif score >= 55:
        temperature = "Warm"

    else:
        temperature = "Cold"

    return score, temperature, ", ".join(reasons)

# =====================================================
# 9. SAVE BUSINESS TO DATABASE
# =====================================================

def save_business(business, city, country):

    score, temperature, reason = calculate_score(business)

    conn = db_connection()

    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR IGNORE INTO city_leads (
        osm_ref,
        name,
        city,
        country,
        category,
        phone,
        email,
        website,
        address,
        latitude,
        longitude,
        score,
        score_reason,
        status,
        created_at,
        updated_at
    )
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        business["osm_ref"],
        business["name"],
        city,
        country,
        business["category"],
        business["phone"],
        business["email"],
        business["website"],
        business["address"],
        business["latitude"],
        business["longitude"],
        score,
        reason,
        "New",
        datetime.now().isoformat(),
        datetime.now().isoformat()
    ))

    inserted = cursor.rowcount > 0

    conn.commit()
    conn.close()

    return inserted

# =====================================================
# 10. GET LEADS
# =====================================================

def get_leads():

    conn = db_connection()

    df = pd.read_sql_query(
        "SELECT * FROM city_leads ORDER BY id DESC",
        conn
    )

    conn.close()

    return df

# =====================================================
# 11. GROQ AI
# =====================================================

def groq_ai(prompt, api_key, model):

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a professional B2B sales assistant. "
                    "Never invent business facts. Clearly label "
                    "assumptions and recommendations."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": 1200
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=60
    )

    if response.status_code != 200:
        raise Exception(response.text)

    data = response.json()

    return data["choices"][0]["message"]["content"]

# =====================================================
# 12. HEADER
# =====================================================

st.markdown("""
<div class="hero">
    <h1>🌍 City-to-City Lead Generation</h1>
    <p>
    Discover businesses in two different cities.
    Save prospects, analyze opportunities and manage sales.
    </p>
</div>
""", unsafe_allow_html=True)

# =====================================================
# 13. SIDEBAR
# =====================================================

st.sidebar.title("🌍 City LeadGen")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "City-to-City Search",
        "My Leads",
        "Sales Pipeline",
        "Groq AI Assistant"
    ]
)

st.sidebar.divider()

st.sidebar.subheader("Groq AI Settings")

groq_key = st.sidebar.text_input(
    "Groq API Key",
    type="password"
)

groq_model = st.sidebar.text_input(
    "Groq Model",
    value="llama-3.3-70b-versatile"
)

st.sidebar.caption(
    "AI key is used for this session only. "
    "Do not share it or upload it to GitHub."
)

# =====================================================
# 14. DASHBOARD
# =====================================================

df = get_leads()

if page == "Dashboard":

    st.subheader("📊 Worldwide Business Dashboard")

    total = len(df)

    city_count = (
        df["city"].nunique()
        if total else 0
    )

    hot = (
        int((df["score"] >= 75).sum())
        if total else 0
    )

    won = (
        int((df["status"] == "Won").sum())
        if total else 0
    )

    c1, c2, c3, c4 = st.columns(4)

    metrics = [
        ("Total Leads", total),
        ("Cities Covered", city_count),
        ("Hot Leads", hot),
        ("Deals Won", won)
    ]

    for col, (label, value) in zip(
        [c1, c2, c3, c4],
        metrics
    ):

        with col:

            st.markdown(
                f"""
                <div class="metric-card">
                    <p>{label}</p>
                    <h2>{value}</h2>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.write("")

    if total:

        left, right = st.columns(2)

        with left:

            st.subheader("Leads by City")

            st.bar_chart(
                df["city"].value_counts()
            )

        with right:

            st.subheader("Lead Status")

            st.bar_chart(
                df["status"].value_counts()
            )

        st.subheader("Latest Leads")

        st.dataframe(
            df.head(15),
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Abhi koi lead nahi hai. City-to-City Search se shuru karein."
        )

# =====================================================
# 15. CITY-TO-CITY SEARCH
# =====================================================

elif page == "City-to-City Search":

    st.subheader("🔎 Search Two Cities Separately")

    st.write(
        "Dono cities ke business results alag alag database mein save honge."
    )

    with st.form("city_search_form"):

        st.markdown("### 🏙️ First City")

        c1, c2 = st.columns(2)

        city1 = c1.text_input(
            "City 1",
            placeholder="London"
        )

        country1 = c2.text_input(
            "Country 1",
            placeholder="United Kingdom"
        )

        st.divider()

        st.markdown("### 🏙️ Second City")

        c3, c4 = st.columns(2)

        city2 = c3.text_input(
            "City 2",
            placeholder="Dubai"
        )

        country2 = c4.text_input(
            "Country 2",
            placeholder="United Arab Emirates"
        )

        st.divider()

        category = st.selectbox(
            "Business Type",
            list(CATEGORY_FILTERS.keys())
        )

        radius = st.slider(
            "Search radius around each city (km)",
            min_value=1,
            max_value=20,
            value=5
        )

        result_limit = st.slider(
            "Maximum results per city",
            min_value=10,
            max_value=200,
            value=50,
            step=10
        )

        search_button = st.form_submit_button(
            "🌍 Search Both Cities",
            type="primary",
            use_container_width=True
        )

    if search_button:

        if not all([
            city1.strip(),
            country1.strip(),
            city2.strip(),
            country2.strip()
        ]):

            st.error(
                "Please enter both cities and their countries."
            )

        elif (
            city1.strip().lower() == city2.strip().lower()
            and country1.strip().lower() == country2.strip().lower()
        ):

            st.error(
                "Please select two different cities."
            )

        else:

            city_configs = [
                (city1.strip(), country1.strip()),
                (city2.strip(), country2.strip())
            ]

            total_found = 0
            total_saved = 0

            for index, (city, country) in enumerate(
                city_configs
            ):

                st.markdown(
                    f"### {'1️⃣' if index == 0 else '2️⃣'} "
                    f"{city}, {country}"
                )

                try:

                    with st.spinner(
                        f"Finding businesses in {city}..."
                    ):

                        lat, lon = get_city_location(
                            city,
                            country
                        )

                        elements = search_city_businesses(
                            city,
                            country,
                            lat,
                            lon,
                            radius * 1000,
                            category,
                            result_limit
                        )

                        found = 0
                        saved = 0
                        city_results = []

                        for element in elements:

                            business = extract_business(element)

                            if not business:
                                continue

                            found += 1

                            if save_business(
                                business,
                                city,
                                country
                            ):
                                saved += 1

                            city_results.append({
                                "Business": business["name"],
                                "Category": business["category"],
                                "Phone": business["phone"],
                                "Email": business["email"],
                                "Website": business["website"],
                                "Address": business["address"],
                                "Map": business["maps_url"]
                            })

                    total_found += found
                    total_saved += saved

                    st.success(
                        f"{city}: {found} listings found, "
                        f"{saved} new leads saved."
                    )

                    if city_results:

                        st.dataframe(
                            pd.DataFrame(city_results),
                            use_container_width=True,
                            hide_index=True
                        )

                    else:

                        st.warning(
                            f"No named businesses found in {city}."
                        )

                except Exception as error:

                    st.error(
                        f"Could not search {city}: {error}"
                    )

                # Nominatim public service ke liye
                # requests ke darmiyan delay.
                if index == 0:
                    time.sleep(1.1)

            st.divider()

            st.success(
                f"Search complete! Total listings: {total_found}. "
                f"New leads saved: {total_saved}."
            )

            st.info(
                "OpenStreetMap data attribution: "
                "© OpenStreetMap contributors."
            )

# =====================================================
# 16. MY LEADS
# =====================================================

elif page == "My Leads":

    st.subheader("📇 Saved Business Leads")

    df = get_leads()

    if df.empty:

        st.info("No saved leads yet.")

    else:

        c1, c2 = st.columns(2)

        city_filter = c1.selectbox(
            "Filter by City",
            ["All"] + sorted(
                df["city"].dropna().unique().tolist()
            )
        )

        status_filter = c2.selectbox(
            "Filter by Status",
            ["All"] + sorted(
                df["status"].dropna().unique().tolist()
            )
        )

        filtered = df.copy()

        if city_filter != "All":

            filtered = filtered[
                filtered["city"] == city_filter
            ]

        if status_filter != "All":

            filtered = filtered[
                filtered["status"] == status_filter
            ]

        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "⬇️ Download Leads CSV",
            filtered.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="city_to_city_leads.csv",
            mime="text/csv"
        )

        st.divider()

        st.subheader("Update Lead")

        selected_id = st.selectbox(
            "Select Lead ID",
            filtered["id"].tolist()
        )

        selected = filtered[
            filtered["id"] == selected_id
        ].iloc[0]

        with st.form("update_lead_form"):

            new_status = st.selectbox(
                "Sales Status",
                [
                    "New",
                    "Contacted",
                    "Interested",
                    "Meeting",
                    "Proposal",
                    "Won",
                    "Lost"
                ],
                index=[
                    "New",
                    "Contacted",
                    "Interested",
                    "Meeting",
                    "Proposal",
                    "Won",
                    "Lost"
                ].index(selected["status"])
                if selected["status"] in [
                    "New",
                    "Contacted",
                    "Interested",
                    "Meeting",
                    "Proposal",
                    "Won",
                    "Lost"
                ] else 0
            )

            notes = st.text_area(
                "Notes",
                value=selected["notes"] or ""
            )

            update_button = st.form_submit_button(
                "Update Lead",
                type="primary"
            )

        if update_button:

            conn = db_connection()

            conn.execute("""
            UPDATE city_leads
            SET status=?, notes=?, updated_at=?
            WHERE id=?
            """, (
                new_status,
                notes,
                datetime.now().isoformat(),
                int(selected_id)
            ))

            conn.commit()
            conn.close()

            st.success("Lead updated successfully.")

            st.rerun()

        if selected["website"]:

            st.link_button(
                "Open Business Website",
                selected["website"]
            )

        if selected["latitude"] and selected["longitude"]:

            map_url = (
                f"https://www.openstreetmap.org/"
                f"?mlat={selected['latitude']}"
                f"&mlon={selected['longitude']}"
            )

            st.link_button(
                "Open Business Map",
                map_url
            )

# =====================================================
# 17. SALES PIPELINE
# =====================================================

elif page == "Sales Pipeline":

    st.subheader("📈 Sales Pipeline")

    df = get_leads()

    stages = [
        "New",
        "Contacted",
        "Interested",
        "Meeting",
        "Proposal",
        "Won",
        "Lost"
    ]

    if df.empty:

        st.info("No leads available.")

    else:

        counts = df["status"].value_counts()

        cols = st.columns(4)

        for col, stage in zip(cols, stages[:4]):

            with col:

                st.metric(
                    stage,
                    int(counts.get(stage, 0))
                )

        st.bar_chart(counts)

        st.subheader("City-wise Sales Progress")

        pivot = pd.crosstab(
            df["city"],
            df["status"]
        )

        st.dataframe(
            pivot,
            use_container_width=True
        )

# =====================================================
# 18. GROQ AI ASSISTANT
# =====================================================

elif page == "Groq AI Assistant":

    st.subheader("🤖 AI Sales Assistant")

    df = get_leads()

    if df.empty:

        st.warning("Search and save businesses first.")

    elif not groq_key:

        st.warning(
            "Groq API key sidebar mein enter karein."
        )

        st.link_button(
            "Get Groq API Key",
            "https://console.groq.com/keys"
        )

    else:

        selected_id = st.selectbox(
            "Select Business",
            df["id"].tolist(),
            format_func=lambda x:
            f"{x} - {df.loc[df.id == x, 'name'].iloc[0]}"
        )

        lead = df[
            df["id"] == selected_id
        ].iloc[0]

        task = st.selectbox(
            "AI Task",
            [
                "Analyze Business Lead",
                "Create WhatsApp Message",
                "Create Sales Email",
                "Recommend Software Service",
                "Create Sales Proposal"
            ]
        )

        st.write("### Selected Business")

        st.write("**Name:**", lead["name"])
        st.write("**City:**", lead["city"])
        st.write("**Country:**", lead["country"])
        st.write("**Category:**", lead["category"])
        st.write("**Website:**", lead["website"] or "Not listed")
        st.write("**Phone:**", lead["phone"] or "Not listed")
        st.write("**Lead Score:**", lead["score"])

        if st.button(
            "Generate with Groq AI",
            type="primary"
        ):

            prompt = f"""
            Business information:

            Name: {lead['name']}
            City: {lead['city']}
            Country: {lead['country']}
            Category: {lead['category']}
            Website: {lead['website']}
            Phone: {lead['phone']}
            Email: {lead['email']}
            Lead score: {lead['score']}

            Task: {task}

            We are a software house selling:
            - Websites
            - Mobile applications
            - AI chatbots
            - Business management software
            - Workflow automation

            Provide a professional, personalized result.

            Do not invent facts about the business.
            Clearly identify assumptions.
            Do not claim that the business needs a service
            unless the provided data confirms it.
            """

            try:

                with st.spinner("Groq AI is working..."):

                    result = groq_ai(
                        prompt,
                        groq_key,
                        groq_model
                    )

                st.markdown("### AI Result")

                st.markdown(result)

                st.download_button(
                    "Download AI Result",
                    result,
                    file_name="ai_sales_result.txt"
                )

            except Exception as error:

                st.error(
                    f"Groq API error: {error}"
                )

# =====================================================
# 19. FOOTER
# =====================================================

st.divider()

st.caption(
    "City-to-City Worldwide Lead Generator | "
    "Business data © OpenStreetMap contributors | "
    "Use public contact information responsibly."
)
