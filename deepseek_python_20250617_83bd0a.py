import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import PyPDF2
import io
from urllib.parse import urljoin
import time

# Set page config
st.set_page_config(
    page_title="CDSCO SEC PDF Search",
    page_icon="🔍",
    layout="wide"
)

# Correct CDSCO SEC URL
CDSCO_BASE_URL = "https://cdsco.gov.in/opencms/opencms/en/Notifications/Safety-Notices/"

# Cache the PDF scraping and parsing to improve performance
@st.cache_data(ttl=24*3600)  # Cache for 24 hours
def get_all_pdf_links(base_url):
    """Get all PDF links from the CDSCO SEC website"""
    try:
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        pdf_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.lower().endswith('.pdf'):
                full_url = urljoin(base_url, href)
                pdf_links.append(full_url)
        
        # Also check if there are paginated results
        pagination = soup.find('ul', class_='pagination')
        if pagination:
            st.info("Found paginated results. This might take a while to process all pages...")
            page_links = [urljoin(base_url, a['href']) for a in pagination.find_all('a', href=True)]
            for page_url in set(page_links):  # Remove duplicates
                try:
                    page_resp = requests.get(page_url, timeout=10)
                    page_resp.raise_for_status()
                    page_soup = BeautifulSoup(page_resp.text, 'html.parser')
                    for link in page_soup.find_all('a', href=True):
                        href = link['href']
                        if href.lower().endswith('.pdf'):
                            full_url = urljoin(page_url, href)
                            pdf_links.append(full_url)
                except Exception as e:
                    st.warning(f"Could not process page {page_url}: {e}")
        
        return list(set(pdf_links))  # Remove duplicate URLs
    except Exception as e:
        st.error(f"Error fetching PDF links: {e}")
        return []

@st.cache_data(ttl=24*3600)
def extract_text_from_pdf(pdf_url):
    """Extract text from a PDF file"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(pdf_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        with io.BytesIO(response.content) as f:
            try:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() or ""
                return text
            except PyPDF2.errors.PdfReadError:
                # Try OCR approach for scanned PDFs (would require additional dependencies)
                return ""
    except Exception as e:
        st.warning(f"Could not read PDF {pdf_url}: {e}")
        return ""

def search_keyword_in_pdfs(pdf_links, keyword):
    """Search for keyword in all PDFs and return matching PDFs with context"""
    results = []
    keyword = keyword.lower()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, pdf_url in enumerate(pdf_links):
        status_text.text(f"Processing PDF {i+1}/{len(pdf_links)}: {pdf_url.split('/')[-1]}")
        progress_bar.progress((i + 1) / len(pdf_links))
        
        text = extract_text_from_pdf(pdf_url)
        if not text:
            continue
            
        text_lower = text.lower()
        if keyword in text_lower:
            # Find all occurrences with context
            occurrences = []
            pattern = re.compile(r'(.{0,30}' + re.escape(keyword) + r'.{0,30})', re.IGNORECASE)
            for match in pattern.finditer(text):
                occurrences.append(match.group(1).strip())
            
            # Limit to first 5 occurrences to avoid too much text
            occurrences = occurrences[:5]
            results.append({
                'url': pdf_url,
                'occurrences': occurrences,
                'count': text_lower.count(keyword),
                'filename': pdf_url.split('/')[-1]
            })
        
        # Small delay to be polite to the server
        time.sleep(0.5)
    
    progress_bar.empty()
    status_text.empty()
    
    return results

# Main app
def main():
    st.title("🔍 CDSCO Safety Notices PDF Search Tool")
    st.markdown("""
    This tool searches through PDF documents available on the CDSCO Safety Notices page 
    for your specified keywords and returns matching documents with context.
    """)
    
    with st.expander("⚙️ Search Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            keyword = st.text_input("Enter keyword to search", 
                                 placeholder="e.g., drug name, adverse event")
        with col2:
            min_matches = st.number_input("Minimum matches per document", 
                                       min_value=1, value=1)
    
    if st.button("Search PDFs") and keyword:
        with st.spinner("Fetching PDF links from CDSCO website..."):
            pdf_links = get_all_pdf_links(CDSCO_BASE_URL)
        
        if not pdf_links:
            st.error("No PDFs found on the CDSCO Safety Notices page.")
            return
            
        st.info(f"Found {len(pdf_links)} PDF documents. Now searching for '{keyword}'...")
        
        results = search_keyword_in_pdfs(pdf_links, keyword)
        
        if not results:
            st.warning(f"No documents found containing '{keyword}'.")
            return
            
        st.success(f"Found {len(results)} documents containing '{keyword}'")
        
        for result in sorted(results, key=lambda x: x['count'], reverse=True):
            if result['count'] < min_matches:
                continue
                
            with st.expander(f"📄 {result['filename']} ({result['count']} matches)"):
                st.markdown(f"**PDF URL:** [{result['filename']}]({result['url']})")
                st.markdown(f"**Total occurrences:** {result['count']}")
                
                st.markdown("**Sample occurrences:**")
                for occurrence in result['occurrences']:
                    # Highlight the keyword in the text
                    highlighted = re.sub(
                        re.escape(keyword), 
                        lambda match: f"**{match.group(0)}**", 
                        occurrence, 
                        flags=re.IGNORECASE
                    )
                    st.markdown(f"- {highlighted}")
    
    elif not keyword:
        st.warning("Please enter a search keyword")

if __name__ == "__main__":
    main()