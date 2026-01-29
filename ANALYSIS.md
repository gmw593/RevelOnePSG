# RevelOnePSG Bulk Upload Tool - Issue Analysis

**Date:** 2026-01-29
**Analyst:** Claude (with Keith)
**Reported By:** Loizos Karaiskos (Slack, 9:42 AM)

---

## Executive Summary

Two issues were reported with the bulk upload tool:
1. **Companies aren't showing up in Revel Reports** after adding candidates via the tool
2. **Location data showing states instead of cities** for candidates added via the import tool

This analysis traces the data flow through all three n8n workflows and identifies the root causes.

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA FLOW DIAGRAM                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  LinkedIn CSV Export                                                         │
│        │                                                                     │
│        ▼                                                                     │
│  ┌──────────────┐                                                           │
│  │  Streamlit   │  main.py - File upload, data display                      │
│  │  Frontend    │  Hosted on Render                                         │
│  └──────┬───────┘                                                           │
│         │                                                                    │
│         ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │  WORKFLOW 1: Bulk-1 Send to rocketreach                          │       │
│  │  Webhook: d038ef22-7924-4b5c-a7bd-d5bc2bacd5f0                   │       │
│  │  Purpose: Enrich candidates with email addresses                 │       │
│  └──────┬───────────────────────────────────────────────────────────┘       │
│         │                                                                    │
│         ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │  WORKFLOW 2: Bulk-2 Search for or Create Candidates              │       │
│  │  Webhook: 9ddc6dd0-d758-4b17-8ff0-efe8988e577f                   │       │
│  │  Purpose: Create/find contacts in HubSpot                        │       │
│  └──────┬───────────────────────────────────────────────────────────┘       │
│         │                                                                    │
│         ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │  WORKFLOW 3: Bulk-3 Search for or create candidate trackers      │       │
│  │  Webhook: 389f2b39-2c32-43ee-8ad7-cfc34def0980                   │       │
│  │  Purpose: Create candidate tracker records, associate with search│       │
│  └──────┬───────────────────────────────────────────────────────────┘       │
│         │                                                                    │
│         ▼                                                                    │
│  ┌──────────────┐                                                           │
│  │   HubSpot    │  Contacts + Candidate Trackers + Searches                 │
│  └──────┬───────┘                                                           │
│         │                                                                    │
│         ▼                                                                    │
│  ┌──────────────┐                                                           │
│  │ Revel Reports│  Google Sheets (pulls from HubSpot)                       │
│  └──────────────┘                                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Issue 1: Companies Not Showing in Revel Reports

### Symptom
Companies aren't appearing in Revel Reports for candidates added via the bulk upload tool.

### Data Flow Trace

#### Step 1: CSV Input
**File:** `pipeline_export (47).csv`

The LinkedIn export contains a `Current Company` column with valid data:
```csv
"First Name","Last Name",...,"Current Company",...
"Erin","Kavanagh",...,"Datafold",...
"Jenny","Fong",...,"Apptio, an IBM Company",...
"Kamal","Thakarsey",...,"Stellic",...
```

**Status:** ✅ Company data is present in source CSV

#### Step 2: Streamlit Frontend
**File:** `main.py:48-50`

```python
file = st.file_uploader("Upload Linkedin CSV Export", type="csv")
if file:
    st.session_state.table = pd.read_csv(file)
```

The CSV is read directly into a pandas DataFrame. No transformation occurs.

**Status:** ✅ Company data passes through unchanged

#### Step 3: Workflow 1 - RocketReach Enrichment
**File:** `Bulk-1 Send to rocketreach.json`

The "Add email to person list" node (lines 61-130) explicitly maps `Current Company`:

```json
{
  "id": "5afac7e5-1b1a-4783-9d5d-37874d6f96e5",
  "name": "Current Company",
  "value": "={{ $('Extract Body').item.json['Current Company'] }}",
  "type": "string"
}
```

**Status:** ✅ Company data is preserved through Workflow 1

#### Step 4: Workflow 2 - Contact Creation in HubSpot
**File:** `Bulk-2 Search for or Create Candidates.json`

Two nodes create contacts - one with email (line 420) and one without (line 494).

**"Create Contact w/Email" node (line 420):**
```json
{
  "properties": {
    "firstname": "{{ $('Extract Body').item.json['First Name'] }}",
    "lastname": "{{ $('Extract Body').item.json['Last Name'] }}",
    "jobtitle": "{{ $('Extract Body').item.json['Current Title'] }}",
    "email": "{{ $('Extract Body').item.json.recommended_personal_email }}",
    "company": "{{ $('Extract Body').item.json['Current Company'] }}",
    "city": "{{ $('Extract Body').item.json.Location }}",
    "hs_linkedin_url": "{{ $('Extract Body').item.json['Profile URL'] }}",
    "bulk_upload_user": "{{ $('Turn to body').item.json.user }}"
  }
}
```

**Status:** ✅ Company is being set on the HubSpot Contact record via the `company` property

#### Step 5: Workflow 3 - Candidate Tracker Creation
**File:** `Bulk-3 Search for or create candidate trackers.json`

**"Get a contact" node (lines 310-342):**
This node fetches contact properties before creating the tracker:
```json
{
  "properties": [
    "jobtitle",
    "city",
    "linkedin_url__normalized_",
    "company"
  ]
}
```

**"Create Candidate Tracker" node (lines 231-260):**
```json
{
  "properties": {
    "stage": "{{ $('Loop Over Candidates').item.json.First }} {{ $('Loop Over Candidates').item.json.Last }} - {{ $('Loop Over Candidates').item.json['Search Info'].role_name }} - {{ $('Loop Over Candidates').item.json.properties.role_id }}",
    "contact_first_name": "{{ $('Loop Over Candidates').item.json.First }}",
    "contact_last_name": "{{ $('Loop Over Candidates').item.json.Last }}",
    "job_title": "{{ $json.properties.jobtitle.value }}",
    "company_name": "{{ $json.properties.company.value }}",
    "linkedin_url": "{{ $json.properties.linkedin_url__normalized_ }}",
    "city": "{{ $json.properties.city.value }}",
    ...
  }
}
```

### Root Cause Analysis

#### Potential Issue A: Inconsistent Property Access Pattern

In the "Create Candidate Tracker" JSON, there's an inconsistency in how properties are accessed:

| Property | Access Pattern | Notes |
|----------|---------------|-------|
| `job_title` | `$json.properties.jobtitle.value` | Uses `.value` suffix |
| `company_name` | `$json.properties.company.value` | Uses `.value` suffix |
| `linkedin_url` | `$json.properties.linkedin_url__normalized_` | NO `.value` suffix |
| `city` | `$json.properties.city.value` | Uses `.value` suffix |

The HubSpot "Get Contact" node returns properties in different formats depending on the `propertyMode` setting:

- **`propertyMode: "valueOnly"`** (line 324): Returns `{ property: "value" }` format
- **`propertyMode: "valueAndHistory"`**: Returns `{ property: { value: "...", versions: [...] } }` format

Looking at line 316-326:
```json
{
  "propertiesCollection": {
    "propertiesValues": {
      "properties": ["jobtitle", "city", "linkedin_url__normalized_", "company"],
      "propertyMode": "valueOnly"
    }
  }
}
```

**The mode is `valueOnly`**, which means properties are returned as simple values, NOT as objects with a `.value` property.

**🔴 ROOT CAUSE IDENTIFIED:** The access pattern `$json.properties.company.value` is WRONG when `propertyMode` is `valueOnly`. It should be `$json.properties.company` (without `.value`).

#### Potential Issue B: LinkedIn URL Property Inconsistency

Notice that `linkedin_url` is accessed WITHOUT `.value`:
```json
"linkedin_url": "{{ $json.properties.linkedin_url__normalized_ }}"
```

But other properties use `.value`. This suggests someone already fixed the linkedin_url but forgot to fix the others, OR the linkedin_url was always broken in a different way.

### Verification Needed

1. **Check HubSpot Contact directly:** Look up a recently bulk-uploaded contact (e.g., "Erin Kavanagh") in HubSpot. Does the `company` field have a value?
   - If YES: The issue is in Workflow 3 (tracker creation)
   - If NO: The issue is in Workflow 2 (contact creation)

2. **Check n8n execution logs:** Look at a recent execution of Workflow 3. What does the output of "Get a contact" look like? Is it:
   - `{ properties: { company: "Datafold" } }` (valueOnly format)
   - `{ properties: { company: { value: "Datafold" } } }` (full format)

3. **Check Revel Report data source:** Does Revel Reports pull `company_name` from the Candidate Tracker, or does it pull `company` from the associated Contact?

---

## Issue 2: Location Showing States Instead of Cities

### Symptom
In Revel Reports, candidate locations are showing states (e.g., "California") instead of cities (e.g., "San Francisco").

### Data Flow Trace

#### Step 1: CSV Input
**File:** `pipeline_export (47).csv`

The LinkedIn `Location` field contains various formats:
```
"San Francisco"              ← City only
"San Francisco Bay Area"     ← Metro area
"Washington DC-Baltimore Area" ← Multi-city region
"Portland, Oregon Metropolitan Area" ← Metro with state name
```

Sample from the actual CSV:
| First Name | Location |
|------------|----------|
| Erin | San Francisco |
| Jenny | San Francisco Bay Area |
| Kamal | San Francisco |
| Jason | San Francisco |
| Michael | San Francisco Bay Area |
| Cari | San Francisco Bay Area |

**Status:** ⚠️ Location data is city-level or metro-area level, NOT state-level

#### Step 2: Workflow 2 - Contact Creation
**File:** `Bulk-2 Search for or Create Candidates.json:420`

```json
"city": "{{ $('Extract Body').item.json.Location }}"
```

The LinkedIn `Location` field is mapped directly to HubSpot's `city` field with NO parsing or transformation.

#### Step 3: Workflow 3 - Tracker Creation
**File:** `Bulk-3 Search for or create candidate trackers.json:244`

```json
"city": "{{ $json.properties.city.value }}"
```

The city is copied from the Contact to the Tracker (with the same `.value` issue noted above).

### Root Cause Analysis

The reported symptom ("states showing instead of cities") doesn't match what we see in the CSV data. The CSV contains:
- City names: "San Francisco", "Austin", "Denver"
- Metro areas: "San Francisco Bay Area", "Portland, Oregon Metropolitan Area"

**Possible explanations:**

1. **Different CSV/data source:** The problematic data may have come from a different LinkedIn export with different location formatting.

2. **HubSpot field transformation:** HubSpot may have a state field that gets auto-populated based on the city field, and Revel Reports may be pulling the wrong field.

3. **Revel Report configuration:** The Google Sheet formula may be pulling from the wrong HubSpot property.

4. **Metro area parsing issue:** Values like "Portland, Oregon Metropolitan Area" contain state names, which could be getting extracted incorrectly somewhere.

### Verification Needed

1. **Get a specific example:** Ask Loizos for a specific candidate name that shows a state instead of a city in Revel Reports.

2. **Check HubSpot fields:** For that candidate, check what values are in:
   - Contact → `city` field
   - Contact → `state` field (if exists)
   - Candidate Tracker → `city` field

3. **Check Revel Report formula:** What HubSpot field does the LOCATION column in Revel Reports pull from?

---

## Sample Data Analysis

### Input CSV: `pipeline_export (47).csv`

| Row | First Name | Last Name | Current Company | Location |
|-----|------------|-----------|-----------------|----------|
| 1 | Erin | Kavanagh | Datafold | San Francisco |
| 2 | Jenny | Fong | Apptio, an IBM Company | San Francisco Bay Area |
| 3 | Kamal | Thakarsey | Stellic | San Francisco |
| 4 | Jason | Garoutte | Galileo | San Francisco |
| 5 | Michael | Ortega | Rubrik | San Francisco Bay Area |
| 6 | Erich | Ziegler | MaintainX | San Francisco |
| 7 | Greg | Howard | GH Marketing | San Francisco |
| 8 | Megan | Bouhamama | vFunction | San Francisco |
| 9 | Junie | Dinda | Instabase | San Francisco |
| 10 | Cari | (Goodrich) Cicchetti | Coalition Operators | San Francisco Bay Area |

### CSV Quality Issues Noted

1. **Multiline text in Notes/Feedback fields:** Rows 2-7, 9-10, 11-14, 19-23 have multiline text with embedded quotes. This could cause parsing issues.

2. **Trailing spaces in names:** e.g., `"(Goodrich) Cicchetti "` has a trailing space.

3. **Special characters:** Unicode en-dash `‑` in some text (e.g., "Kubernetes‑optimized").

4. **Empty Email/Phone columns:** These are expected to be filled by RocketReach.

---

## Revel Report Structure

**File:** `Revel Report - Director of Category Growth - Hims & Hers.xlsx`

### Sheet: "Candidates Contacted"

| Column | Field Name | Description |
|--------|------------|-------------|
| 0 | GROUP | Candidate grouping |
| 1 | NAME | Full name |
| 2 | STAGE | Pipeline stage |
| 3 | TITLE | Job title |
| 4 | COMPANY | Company name |
| 5 | LOCATION | Location/city |
| 6 | LINKEDIN | LinkedIn URL |
| 7 | INTERVIEW NOTES | Link to notes doc |
| ... | ... | ... |

### Sample Data from Report

| NAME | COMPANY | LOCATION |
|------|---------|----------|
| Max Baker | Peloton Interactive | New York |
| Lily (Hou) George | Wayfair | Boston |

This particular report shows clean data, likely from manual entry or a different data source.

---

## Recommended Fixes

### Fix 1: Correct Property Access Pattern in Workflow 3

**File:** `Bulk-3 Search for or create candidate trackers.json`
**Node:** "Create Candidate Tracker" (line 244)

**Current (BROKEN):**
```json
"job_title": "{{ $json.properties.jobtitle.value }}",
"company_name": "{{ $json.properties.company.value }}",
"city": "{{ $json.properties.city.value }}",
```

**Fixed:**
```json
"job_title": "{{ $json.properties.jobtitle }}",
"company_name": "{{ $json.properties.company }}",
"city": "{{ $json.properties.city }}",
```

OR change the "Get a contact" node to use `propertyMode: "valueAndHistory"` instead of `"valueOnly"`.

### Fix 2: Add Location Parsing (Optional Enhancement)

If needed, add a Code node in Workflow 2 to parse Location into City and State:

```javascript
// Parse LinkedIn location into city/state
const location = $json.Location || '';

let city = location;
let state = '';

// Handle "City, State" format
if (location.includes(', ')) {
  const parts = location.split(', ');
  city = parts[0];
  state = parts[1].replace(' Metropolitan Area', '').replace(' Area', '');
}

// Handle "City Metropolitan Area" format
if (location.includes(' Metropolitan Area')) {
  city = location.replace(' Metropolitan Area', '');
}

// Handle "City Bay Area" format
if (location.includes(' Bay Area')) {
  city = location.replace(' Bay Area', '');
}

return { city, state };
```

### Fix 3: Add Data Validation in Streamlit (Optional Enhancement)

**File:** `main.py`

Add validation before sending to Workflow 1:

```python
# Validate required columns exist
required_columns = ['First Name', 'Last Name', 'Current Company', 'Location', 'Profile URL']
missing = [col for col in required_columns if col not in st.session_state.table.columns]
if missing:
    st.error(f"Missing required columns: {missing}")
    st.stop()

# Warn about empty values
for col in required_columns:
    empty_count = st.session_state.table[col].isna().sum()
    if empty_count > 0:
        st.warning(f"{empty_count} rows have empty {col}")
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `main.py` | Streamlit frontend application |
| `Bulk-1 Send to rocketreach.json` | n8n workflow - RocketReach email enrichment |
| `Bulk-2 Search for or Create Candidates.json` | n8n workflow - HubSpot contact creation |
| `Bulk-3 Search for or create candidate trackers.json` | n8n workflow - Candidate tracker creation |
| `pipeline_export (47).csv` | Sample problematic CSV from Frances |
| `Revel Report - Director of Category Growth - Hims & Hers.xlsx` | Sample Revel Report export |

---

## HubSpot Object IDs

| Object | ID | Description |
|--------|-----|-------------|
| Contacts | `0-1` | Standard HubSpot contact object |
| Searches | `2-30586852` | Custom object for job searches |
| Candidate Trackers | `2-35759116` | Custom object for candidate tracking |

---

## n8n Webhook URLs

| Workflow | Webhook URL |
|----------|-------------|
| Bulk-1 | `https://revelone.app.n8n.cloud/webhook/d038ef22-7924-4b5c-a7bd-d5bc2bacd5f0` |
| Bulk-2 | `https://revelone.app.n8n.cloud/webhook/9ddc6dd0-d758-4b17-8ff0-efe8988e577f` |
| Bulk-3 | `https://revelone.app.n8n.cloud/webhook/389f2b39-2c32-43ee-8ad7-cfc34def0980` |

---

## Next Steps

1. [ ] Verify root cause by checking HubSpot contact record for recently uploaded candidate
2. [ ] Check n8n execution logs for Workflow 3 to see actual property format
3. [ ] Get specific example of candidate with wrong location in Revel Report
4. [ ] Apply Fix 1 to Workflow 3 in n8n
5. [ ] Test with sample CSV upload
6. [ ] Verify fix in Revel Reports

---

## Appendix: Full Workflow Node Lists

### Workflow 1: Bulk-1 Send to rocketreach

1. **Webhook** - Receives data from Streamlit
2. **Turn to body** - Parses JSON body
3. **Extract Body** - Splits out candidate array
4. **Get Emails from RocketReach** - API call to RocketReach
5. **Add email to person list** - Merges email with original data
6. **Combine JSONS** - Aggregates all candidates
7. **Send back to dashboard** - Returns response

### Workflow 2: Bulk-2 Search for or Create Candidates

1. **Webhook** - Receives enriched data
2. **Turn to body** - Parses body, extracts user email
3. **Extract Body** - Splits out candidates
4. **Search for candidate in linkedin** - HubSpot search by LinkedIn URL or name
5. **If Candidate Exists** - Branch based on search results
6. **Response for found contact** - Format response for existing contact
7. **If we have email** - Branch based on email presence
8. **Create Contact w/Email** - Create HubSpot contact with email
9. **Create Contact w/Email1** - Create HubSpot contact without email (placeholder)
10. **Response for created contact** - Format response for new contact
11. **Merge** - Combine all responses
12. **Aggregate** - Combine into single response
13. **Respond to Webhook** - Return to Streamlit

### Workflow 3: Bulk-3 Search for or create candidate trackers

1. **Webhook** - Receives contact data and search ID
2. **Get search info** - Fetch search details from HubSpot
3. **Parse Body** - Extract search_id and candidates
4. **Split Out** - Split candidates array
5. **Edit Fields1** - Add search info to each candidate
6. **Loop Over Candidates** - Process each candidate
7. **Get Trackers of contact** - Get existing tracker associations
8. **Create list of trackers for api call** - Format for batch read
9. **Get tracker details** - Batch read tracker properties
10. **Only work on results** - Extract results array
11. **If not in search** - Check if tracker already exists for this search
12. **Get a contact** - Fetch contact properties (jobtitle, city, linkedin_url, company)
13. **Create Candidate Tracker** - Create new tracker in HubSpot
14. **Tracker Created Response** - Format success response
15. **Get existing Tracker details** - Get details of existing tracker
16. **Tracker Found Response** - Format found response
17. **Aggregate** - Combine all responses
18. **Respond to Webhook** - Return to Streamlit
