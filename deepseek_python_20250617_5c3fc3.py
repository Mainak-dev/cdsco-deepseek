import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import PyPDF2
import io
from urllib.parse import urljoin
import time
import base64

# Set page config
st.set_page_config(
    page_title="CDSCO SEC PDF Search",
    page_icon="🔍",
    layout="wide"
)

# CDSCO SEC URLs
CDSCO_BASE_URL = "https://cdsco.gov.in/opencms/opencms/en/Committees/SEC/"
PDF_BASE_URL = "https://cdsco.gov.in/opencms/opencms/system/modules/CDSCO.WEB/elements/common_download.jsp"

# Cache the PDF scraping and parsing to improve performance
@st.cache_data(ttl=24*3600)
def get_all_pdf_links(base_url):
    """Get all PDF links from the CDSCO SEC website"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        pdf_links = []
        
        # Find all download links - they typically have 'common_download.jsp' in them
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'common_download.jsp' in href:
                # Extract the num_id_pk parameter
                if 'num_id_pk=' in href:
                    num_id = href.split('num_id_pk=')[1]
                    pdf_url = f"{PDF_BASE_URL}?num_id_pk={num_id}"
                    pdf_links.append({
                        'url': pdf_url,
                        'title': link.text.strip(),
                        'id': num_id
                    })
        
        return pdf_links
        
    except Exception as e:
        st.error(f"Error fetching PDF links: {str(e)}")
        return []

@st.cache_data(ttl=24*3600)
def extract_text_from_pdf(pdf_info):
    """Extract text from a PDF file"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(pdf_info['url'], headers=headers, timeout=30)
        response.raise_for_status()
        
        with io.BytesIO(response.content) as f:
            try:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() or ""
                return text
            except PyPDF2.errors.PdfReadError:
                return ""
    except Exception as e:
        st.warning(f"Could not read PDF {pdf_info['title']}: {str(e)}")
        return ""

def search_keyword_in_pdfs(pdf_list, keyword):
    """Search for keyword in all PDFs and return matching PDFs with context"""
    results = []
    keyword = keyword.lower()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, pdf_info in enumerate(pdf_list):
        status_text.text(f"Processing document {i+1}/{len(pdf_list)}: {pdf_info['title']}")
        progress_bar.progress((i + 1) / len(pdf_list))
        
        text = extract_text_from_pdf(pdf_info)
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
                'url': pdf_info['url'],
                'title': pdf_info['title'],
                'occurrences': occurrences,
                'count': text_lower.count(keyword),
                'id': pdf_info['id']
            })
        
        # Small delay to be polite to the server
        time.sleep(1)
    
    progress_bar.empty()
    status_text.empty()
    
    return results

def get_download_link(pdf_id, title):
    """Create a download link for the PDF"""
    pdf_url = f"{PDF_BASE_URL}?num_id_pk={pdf_id}"
    return f'<a href="{pdf_url}" target="_blank" download="{title}.pdf">Download PDF</a>'

# Main app
def main():
    st.title("🔍 CDSCO Subject Expert Committee (SEC) Document Search")
    st.markdown("""
    This tool searches through documents available on the CDSCO SEC website 
    for your specified keywords and returns matching documents with context.
    """)
    
    with st.expander("⚙️ Search Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            keyword = st.text_input("Enter keyword to search", 
                                 placeholder="e.g., drug name, clinical trial")
        with col2:
            min_matches = st.number_input("Minimum matches per document", 
                                       min_value=1, value=1)
    
    if st.button("Search Documents") and keyword:
        with st.spinner("Fetching document links from CDSCO SEC website..."):
            pdf_list = get_all_pdf_links(CDSCO_BASE_URL)
        
        if not pdf_list:
            st.error("No documents found on the CDSCO SEC page.")
            return
            
        st.info(f"Found {len(pdf_list)} documents. Now searching for '{keyword}'...")
        
        results = search_keyword_in_pdfs(pdf_list, keyword)
        
        if not results:
            st.warning(f"No documents found containing '{keyword}'.")
            return
            
        st.success(f"Found {len(results)} documents containing '{keyword}'")
        
        for result in sorted(results, key=lambda x: x['count'], reverse=True):
            if result['count'] < min_matches:
                continue
                
            with st.expander(f"📄 {result['title']} ({result['count']} matches)"):
                st.markdown(f"**Document Title:** {result['title']}")
                
                # Create download link
                download_link = get_download_link(result['id'], result['title'])
                st.markdown(f"**Download:** {download_link}", unsafe_allow_html=True)
                
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