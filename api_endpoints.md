# Fasteignir API Endpoints

### 1. Vísir Fasteignir & Fasteignir.is (The Second Data Source)
Vísir.is and Fasteignir.is share an underlying database built by the software company "Hugsandi Menn". This is a goldmine because it's a completely open REST API, just like MBL's GraphQL API. 

**Live Search Endpoint (Used by Vísir):**
*   **URL:** `https://fasteignir.visir.is/api/search?onpage=1000&page=1`
*   **Method:** `GET`
*   **Auth:** None required.
*   **Response:** Returns a massive JSON array of listings containing `id`, `price`, `size`, `category`, `latitude`, `longitude`, `street_name`, `bedrooms`, `bathrooms`, and image URLs.
*   **Usage:** You can paginate through this using `?page=1`, `?page=2`, etc., making it extremely easy to scrape into the same SQLite database.

**Core REST API (api-beta.fasteignir.is):**
*   **Base URL:** `https://api-beta.fasteignir.is`
*   **Documentation Found:** `https://api-beta.fasteignir.is/doc/introduction`
*   **Key Endpoint:** `GET /properties.json`
*   **Notes:** This is the underlying structural API. While it officially supports Basic Auth for CRUD operations (like agencies posting new listings), the Vísir search endpoint above completely bypasses auth for fetching active public listings.

### 2. MBL Fasteignir (The Primary Source)
As outlined in your project summary, this is a fully open Hasura GraphQL API.
*   **URL:** `https://g.mbl.is/v1/graphql`
*   **Auth:** None required. Introspection enabled.
*   **Notes:** This contains the `fs_purchase_history` (129k rows of actual sale prices vs asking prices), which is the killer feature for the platform's analytics.

### 3. Fastinn.is (The Newest Portal)
Fastinn is a newer, Next.js-based real estate portal.
*   **Status:** After analyzing their frontend network requests, they utilize internal Next.js server actions / TRPC rather than an easily pollable, open REST/GraphQL API. 
*   **Verdict:** Since MBL and Vísir cover ~99% of all listings in Iceland (agencies post to both simultaneously via their CRM software), we don't need to try and scrape Fastinn right now. 
