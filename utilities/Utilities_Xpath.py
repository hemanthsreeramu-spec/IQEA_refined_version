import os
import base64
from typing import Union, IO
import re
import time
from datetime import datetime
import docx2txt
import gitlab
from github import Github, GithubException
from gitlab import Gitlab,GitlabGetError
from collections import defaultdict
from urllib.parse import urlparse
import yaml
import PyPDF2
import random
import utilities.utils_action as action_utils
import time
import string
import json
import ast
import re
import pandas
from io import StringIO
from langchain_core.messages import HumanMessage
from selenium import webdriver
from selenium.common import StaleElementReferenceException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import streamlit as st
from langchain_openai import AzureChatOpenAI
from selenium.webdriver.common.by import By
import pandas as pd
from selenium.webdriver.support.wait import WebDriverWait
import hashlib
from webdriver_manager.chrome import ChromeDriverManager
from uuid import uuid4
from dotenv import load_dotenv
import os
import utilities.db_utils.handler as db_handler

#setting details - source
from config.settings_reader import get_source

source = get_source()

load_dotenv()
current_path = os.getcwd()
output_folder = os.path.join(current_path, "output")
xpath_generator_folder = os.path.join(output_folder, "xpath_generator")
Page_file_generator = os.path.join(output_folder, "page_file_generator")
Test_file_generator = os.path.join(output_folder, "test_file_generator")
xpath_file = os.path.join(xpath_generator_folder, "xpath_details.xlsx")
os.makedirs(xpath_generator_folder, exist_ok=True)
os.makedirs(Page_file_generator, exist_ok=True)
os.makedirs(Test_file_generator, exist_ok=True)


# Check if the Excel file exists
if not os.path.exists(xpath_file):
    # Just create an empty Excel file (without headers)
    with pd.ExcelWriter(xpath_file) as writer:
        pd.DataFrame().to_excel(writer, index=False)
    print(f"Excel file created: {xpath_file}")

def load_prompt_from_file(prompt_type):
    print("********************source**********")
    print(source)
    if source == "file":
        config_folder = os.path.join(os.getcwd(), "Input")
        prompt_file = ""

        if prompt_type == "Web":
            prompt_file = os.path.join(config_folder, "web_prompt.txt")
        elif prompt_type== "PowerBi":
            prompt_file = os.path.join(config_folder, "powerBi_prompt.txt")
        elif prompt_type== "Page_File":
            prompt_file = os.path.join(config_folder, "Page_file_prompt.txt")
        elif prompt_type== "Page_File_Action":
            prompt_file = os.path.join(config_folder, "Page_file_prompt_with_action.txt")
        elif prompt_type== "Test_File_Action":
            prompt_file = os.path.join(config_folder, "test_script_prompt.txt")
        elif prompt_type== "Test_case_generation":
            prompt_file = os.path.join(config_folder, "testcase_generation_final_prompt.txt")
        elif prompt_type== "Test_case_generation_document":
            prompt_file = os.path.join(config_folder, "Testcase_generate_prompt_with_document.txt")
        elif prompt_type== "Test_case_generation_withaction":
            prompt_file = os.path.join(config_folder, "Testcase_generate_prompt_with_action.txt")
        elif prompt_type == "featureaction":
            prompt_file = os.path.join(config_folder, "featureaction_prompt.txt")
        elif prompt_type == "Feature_file":
            prompt_file = os.path.join(config_folder, "featurefile_prompt.txt")
        elif prompt_type== "Test_case_accuracy":
            prompt_file = os.path.join(config_folder, "Testcase_Accuracy_matrix1.txt")
        elif prompt_type == "Test_case_regeneration_accuracy":
            prompt_file = os.path.join(config_folder, "Testcase_regeneration_accuracy.txt")
        elif prompt_type == "Test_case_regeneration_accuracy_doc":
            prompt_file = os.path.join(config_folder, "Testcase_regeneration_accuracy_doc.txt")
        elif prompt_type == "Test_case_regeneration_requirement_split":
            prompt_file = os.path.join(config_folder, "testcase_requirement_split_prompt.txt")
        else:
            raise ValueError(f"Invalid prompt type: {prompt_type}. Expected 'web' or 'powerBi'.")

        if not os.path.exists(prompt_file):
            raise FileNotFoundError(f"Prompt file not found at: {prompt_file}")

        with open(prompt_file, "r", encoding="utf-8") as file:
            prompt_template = file.read()
        print("-------------file- prompttemplate--------------")
        return prompt_template
    elif source == "database":
        prompt_template = db_handler.get_prompt_by_name(prompt_type)
        print("-------------Database- prompttemplate--------------")
        print(prompt_template)
        return prompt_template
    return None

def create_java_file(file_name: str, file_extension: str,response):
    # Ensure the file extension is .java
    if not file_extension.startswith("."):
        if file_extension =="java":
            file_extension = f".{file_extension}"
        elif file_extension =="python":
            file_extension = f".py"
        else:
            file_extension = f".{file_extension}"

    # Full file path with specified directory
    full_file_path = os.path.join(Page_file_generator, f"{file_name}{file_extension}")

    with open(full_file_path, "w") as file:
        file.write(response)

    st.write(f"✅ script generated: {full_file_path}")

def create_test_file(Test_file_location,file_name: str, file_extension: str,response):
    # Ensure the file extension is .java
    if not file_extension.startswith("."):
        if file_extension =="java":
            file_extension = f".{file_extension}"
        elif file_extension =="python":
            file_extension = f".py"
        else:
            file_extension = f".{file_extension}"

    # Full file path with specified directory
    full_file_path = os.path.join(Test_file_location, f"{file_name}{file_extension}")

    with open(full_file_path, "w") as file:
        file.write(response)

    st.write(f"✅ Test file script generated: {full_file_path}")

def get_queries_from_ai(prompt, formatted_summary):
    # Access the variables
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

    # Set the environment variables explicitly if needed
    os.environ["AZURE_OPENAI_API_KEY"] = api_key
    os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint

    model = AzureChatOpenAI(
        openai_api_version="2023-05-15",
        azure_deployment="qepracticekey",
    )
    prompt_template = load_prompt_from_file(prompt)
    print(prompt_template)

    if prompt == "PowerBi":
        #print("formatted_summary:", {formatted_summary})
        formatted_summary_json = json.dumps(formatted_summary, indent=2)
        final_prompt = prompt_template.format(formatted_summary=formatted_summary_json)
        print("Final prompt:", {final_prompt})
        json_list = formatted_summary if isinstance(formatted_summary, list) else json.loads(formatted_summary)
        chunk_size = 15
        json_chunks = [json_list[i:i + chunk_size] for i in range(0, len(json_list), chunk_size)]
        # Collecting responses for all JSON chunks
        all_responses = []
        for i, chunk in enumerate(json_chunks):
            print(f"Processing JSON chunk {i + 1}/{len(json_chunks)}")
            formatted_summary_json = json.dumps(chunk, indent=2)
            final_prompt = prompt_template.format(formatted_summary=formatted_summary_json)

            message = HumanMessage(content=final_prompt)
            output_value = model([message])
            print(f"Response for chunk {i + 1}: {output_value.content}")
            all_responses.append(output_value.content)

        # Combine all responses into one
        combined_response = "\n".join(all_responses)
        return combined_response
    elif prompt == "Web":
        print(formatted_summary)
        #final_prompt = prompt_template.format(formatted_summary=formatted_summary)
        prompt = f"""
From the given list of elements, generate all possible XPath expressions for each element using its tag and attributes only. 
Return only valid XPath strings as output. Do not include any explanation or description. 

Input: {formatted_summary}
Strict Instruction:no ``` or any other wrapper 
"""
        message = HumanMessage(content=prompt)
        output_value = model([message])
        print(output_value)
        return output_value.content
    elif prompt == "Page_File":
        print(formatted_summary)
        message = HumanMessage(content=formatted_summary)
        output_value = model([message])
        print(output_value)
        return output_value.content
    # Split the JSON list if its length exceeds 15

def get_queries_from_ai_duplicate(prompt,formatted_summary):
    prompt_template = load_prompt_from_file(prompt)
    print(prompt_template)
    if prompt=="PowerBI":
        print("formatted_summary:",{formatted_summary})
        formatted_summary_json = json.dumps(formatted_summary, indent=2)
        final_prompt = prompt_template.format(formatted_summary=formatted_summary_json)
    elif prompt=="Web":
        print("formatted_summary:", {formatted_summary})
        final_prompt = prompt_template.format(formatted_summary=formatted_summary)
    # Convert formatted_summary to a JSON-formatted string
    formatted_summary_json = json.dumps(formatted_summary, indent=2)

    final_prompt = prompt_template.format(formatted_summary=formatted_summary_json)
    # Collect visible elements
    os.environ["AZURE_OPENAI_API_KEY"] = "4fed2bedb59744a99b0424622f6d9d1b"
    os.environ["AZURE_OPENAI_ENDPOINT"] = "https://qepracticekey.openai.azure.com/"

    model = AzureChatOpenAI(
        openai_api_version="2023-05-15",
        azure_deployment="qepracticekey",
    )
    message = HumanMessage(content=final_prompt)
    output_value = model([message])
    print(output_value)
    return output_value.content

def is_page_loaded(driver):
    return driver.execute_script("return document.readyState")

def loading_newpage(driver):
    new_page_url = driver.current_url
    print(new_page_url)
    driver.get(new_page_url)
    driver.refresh()
    WebDriverWait(driver, 30).until(is_page_loaded)

def generate_random_prefix(length=8):
    """Generate a random alphanumeric prefix."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def generate_unique_key(element, page_identifier):
    """
    Generate a truly unique key for each visible element.
    The key is based on page identifier, tag name, ID, class, and text content (trimmed).
    """
    tag_name = element.tag_name
    element_id = element.get_attribute("id")
    element_class = element.get_attribute("class")
    element_text = element.text.strip()[:30]  # Limiting text length for clarity

    # Using unique attributes with a fallback to text if ID/Class are absent
    key_parts = [
        page_identifier,
        tag_name,
        f"id={element_id}" if element_id else "no_id",
        f"class={element_class}" if element_class else "no_class",
        f"text={element_text}" if element_text else "no_text"
    ]

    # Generate the base key
    base_key = "|".join(key_parts)

    # Ensuring uniqueness with a counter (auto-increment)
    unique_key = base_key
    counter = 1
    while unique_key in st.session_state:
        unique_key = f"{base_key}|{counter}"
        counter += 1

    return unique_key

def generate_unique_key_duplicate(element,page_identifier='page', prefix='element'):
    """Generate a unique key based on the element's properties."""
    element_str = f"{element.get_attribute('id')}-{element.tag_name}-{element.text.strip()}"
    unique_hash = hashlib.md5(element_str.encode()).hexdigest()
    # Generate the next number from the counter and format it as a 3-digit number
    # Combine prefix, unique hash, and formatted number
    #unique_uuid = uuid.uuid4().hex
    random_prefix = generate_random_prefix()
    return f"{prefix}_{page_identifier}_{unique_hash}_{random_prefix}"

def details_visible_elements(collected_elements,visible_elements,selected_tags,page_identifier):
    for idx, element in enumerate(collected_elements):
        try:
            # if element.is_displayed() and element.is_enabled():
            tag_name = element.tag_name

            # If specific tags are selected or all are allowed
            if "All" in selected_tags or tag_name in selected_tags:
                print(f"[DEBUG] Processing element {idx + 1} with tag: {tag_name}")
                details = {
                    "tag": tag_name,
                    "id": element.get_attribute("id"),
                    "class": element.get_attribute("class"),
                    "name": element.get_attribute("name"),
                    "text": element.text.strip()
                }

                # Filter out empty values
                compact_details = {k: v for k, v in details.items() if v}
                print(f"[DEBUG] Element details: {json.dumps(compact_details, indent=2)}")

                if compact_details:  # Only add if there is meaningful data
                    visible_elements.append(compact_details)

                    # Store for XPath mapping via OpenAI
                    unique_key = generate_unique_key(element, page_identifier)
                    if unique_key not in st.session_state:
                        st.session_state[unique_key] = compact_details
                        print(f"[DEBUG] Unique key stored: {unique_key}")

        except (StaleElementReferenceException, NoSuchElementException) as e:
            print(f"[WARN] Element {idx + 1} skipped due to: {str(e)}")

        except Exception as e:
            print(f"[ERROR] Unexpected error with element {idx + 1}: {str(e)}")

    print(f"[INFO] Total visible elements found inside method: {len(visible_elements)}")
    return visible_elements

def load_config(config_path=None):

    if not config_path:
        config_path = os.path.join(os.getcwd(), "Input", "config.yaml")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at: {config_path}. Please ensure the config file exists.")

    with open(config_path, "r") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict) or "xpaths" not in config:
        raise ValueError("Invalid config file format. Ensure 'xpaths' section is properly defined.")

    xpaths = config.get("xpaths", {})
    if not xpaths:
        raise ValueError("XPath values are missing in the 'xpaths' section.")

    return xpaths

def get_visible_element_powerBi(driver,page_identifier):
    # Collect visible elements
    xpaths = load_config()
    print("Loaded XPaths:", xpaths)
    # Attempt 1: Fetch svg > text nodes
    elements_svg_text = driver.find_elements(By.XPATH, xpaths["elements_svg_text"])

    # Collect elements from both visual-container and SVG text elements
    elements_visual_container = driver.find_elements(By.XPATH, xpaths["elements_visual_container"])
    # Graph specific elements
    graph_label_elements = driver.find_elements(By.XPATH,xpaths["graph_label_elements"])
    graph_tick_elements = driver.find_elements(By.XPATH,xpaths["graph_tick_elements"])
    graph_title_elements = driver.find_elements(By.XPATH,xpaths["graph_title_elements"])
    print(f"SVG text found: {len(elements_svg_text)}")
    print(f"Visual containers found: {len(elements_visual_container)}")
    print(f"Graph labels found: {len(graph_label_elements)}")
    print(f"Graph ticks found: {len(graph_tick_elements)}")
    print(f"Graph titles found: {len(graph_title_elements)}")
    # Merge the lists while avoiding duplicates
    # all_elements = list(set(elements_visual_container + elements_svg_text+graph_label_elements +
    #                         graph_tick_elements +
    #                         graph_title_elements))
    all_elements = (elements_visual_container +
                    elements_svg_text +
                    graph_label_elements +
                    graph_tick_elements +
                    graph_title_elements)
    #print(all_elements)
    visible_elements = []
    unique_elements={}


    for idx, element in enumerate(all_elements):
        try:
            if element.is_displayed() and element.is_enabled():
                tag_name = element.tag_name
                text_content = element.text.strip()
                class_name = element.get_attribute("class")
                # Generate a unique key for deduplication
                unique_key =generate_unique_key(element,"powerBi")
                # If specific tags are selected or all are allowed
                #if "All" in selected_tags or tag_name in selected_tags or tag_name in ["text", "div", "span", "a", "button"]:
                if unique_key not in unique_elements:
                    details = {
                        "tag": tag_name,
                        "id": element.get_attribute("id"),
                        "class": element.get_attribute("class"),
                        "name": element.get_attribute("name"),
                        "aria-label": element.get_attribute("aria-label"),
                        "text": element.text.strip()
                    }

                    # Include only non-empty values
                    compact_details = {k: v for k, v in details.items() if v}

                    if compact_details:
                        visible_elements.append(compact_details)
                        unique_elements[unique_key] = compact_details
                        # Store for XPath mapping via OpenAI
                        session_key = generate_unique_key(element, page_identifier)
                        if unique_key not in st.session_state:
                            st.session_state[session_key] = compact_details

        except (StaleElementReferenceException, NoSuchElementException):
            continue

    print(json.dumps(visible_elements, indent=2))
    print(f"[INFO] Total visible elements found: {len(visible_elements)}")
    return visible_elements

def get_visible_element_iframe(driver, page_identifier, selected_tags):
    visible_elements = []  # To store visible and relevant elements

    print("[INFO] Collecting all elements from the main page...")
    all_elements = driver.find_elements(By.XPATH, "//*")
    print(f"[DEBUG] Total elements on main page: {len(all_elements)}")
    #total_elements.extend(all_elements)

    # Collect elements from each iframe
    iframe_elements = driver.find_elements(By.TAG_NAME, "iframe")
    print(f"[INFO] Total iframes found: {len(iframe_elements)}")
    if len(iframe_elements) > 0:
        for iframe_index, iframe_element in enumerate(iframe_elements):
            print(f"[INFO] Switching to iframe {iframe_index + 1}...")
            try:
                driver.switch_to.frame(iframe_element)
                iframe_subelements = driver.find_elements(By.XPATH, "//*")
                details_visible_elements(iframe_subelements,visible_elements,selected_tags,page_identifier)
                print(f"[DEBUG] Total elements in iframe {iframe_index + 1}: {len(iframe_subelements)}")
            except Exception as e:
                print(f"[WARN] Failed to switch to iframe {iframe_index + 1}: {str(e)}")
            finally:
                try:
                    driver.switch_to.default_content()  # Return to the main page
                except Exception as e:
                    print(f"[ERROR] Failed to switch back to main content: {str(e)}")
    else:
        print("[INFO] No iframes found, directly collecting main page elements...")

    visible_elements=details_visible_elements(all_elements,visible_elements,selected_tags,page_identifier)
    # Return the list of visible, relevant elements
    print(f"[INFO] Total visible elements found: {len(visible_elements)}")
    print(json.dumps(visible_elements, indent=2))
    return visible_elements


def get_visible_element(driver,page_identifier,selected_tags):
    all_elements = driver.find_elements(By.XPATH, "//*")
    visible_elements = []


    # Loop through elements and capture only relevant ones
    for idx, element in enumerate(all_elements):
        try:
            # Ensure the element is visible and not disabled
            if element.is_displayed() and element.is_enabled():

                # Check if the element is a relevant type (text box, checkbox, button, link)
                if element.tag_name in selected_tags:
                    #, 'textarea', 'button', 'select'
                    details = {
                        "tag": element.tag_name,
                        "id": element.get_attribute("id"),
                        "class": element.get_attribute("class"),
                        "name": element.get_attribute("name"),
                        "text": element.text.strip()
                    }

                    # Exclude empty or redundant text (only keep the most relevant ones)
                    compact_details = {k: v for k, v in details.items() if v}

                    # Add to the list of visible elements
                    visible_elements.append(compact_details)
                    # Generate a unique key for each element
                    unique_key = generate_unique_key(element, page_identifier)
                    if unique_key not in st.session_state:
                        st.session_state[unique_key] = unique_key

        except (StaleElementReferenceException, NoSuchElementException) as e:
            # Handle exceptions
            #print(f"Element skipped due to: {e}")
            continue

    # Return the list of visible, relevant elements
    print(visible_elements)
    return visible_elements



key=None
def selecting_xpath(details):

    sections = details.strip().split('\n\n')
    print("sections is displayed as:")
    print(sections)
    xpath_dict = {}
    for section in sections:
        print("section is displayed " +section)
        xpaths=[]
        global key
        #key = None
        if '\n' in section:
            lines = section.split('\n')
            print("Lines are displaed as")
            print(lines)
            if lines:
                #key = lines[0].replace(" Variations:", "")
                #print("key is displayed as"+key)
                if "//" in lines[0]:
                    xpaths = lines
                else:
                    xpaths = lines[1:]
                print("xpatha are displayed as")
                print(xpaths)
        else:
            key=section
            print("key is displayed as" + key)
        if xpaths:
            if key:
                print("key available:",key)
                xpath_dict[key] = xpaths
                key = None
            elif key is None:
                print("key not available", key)
                key = lines[0].replace(" Variations:", "")
                print("key from lines", key)
                xpath_dict[key] = xpaths
                key=None
    print("xpath_dict:",xpath_dict)
    return xpath_dict

# Filter out duplicate xpaths before passing to UI
def filter_duplicate_xpaths(xpath_dict):
    unique_entries = set()
    filtered_xpath_dict = {}

    for element, xpaths in xpath_dict.items():
        filtered = []
        for xpath in xpaths:
            key = f"{element}_{xpath}"
            if key not in unique_entries:
                unique_entries.add(key)
                filtered.append(xpath)
        if filtered:
            filtered_xpath_dict[element] = filtered
    return filtered_xpath_dict
def adding_xapth_user_view(xpath_dict):
    print("goind to add element")
    try:
        for element, xpaths in xpath_dict.items():
            st.subheader(f"{element}")
            for xpath in xpaths:
                if xpath.strip():
                    # unique_id = uuid.uuid4().hex[:8]
                    # checkbox_key = f"{element}_{xpath}_{unique_id}"
                    checkbox_key = hashlib.md5(f"{element}_{xpath}".encode()).hexdigest()
                    # Display checkbox and maintain state
                    print("st.session_state.selected_xpaths", st.session_state.selected_xpaths)
                    try:
                        if st.checkbox(xpath, key=checkbox_key):
                            print("st.session_state.selected_xpaths", st.session_state.selected_xpaths)
                            if {"Element": element, "XPath": xpath} not in st.session_state.selected_xpaths:
                                st.session_state.selected_xpaths.append({"Element": element, "XPath": xpath})
                        else:
                            print("st.session_state.selected_xpaths", st.session_state.selected_xpaths)
                            st.session_state.selected_xpaths = [
                                x for x in st.session_state.selected_xpaths if x["XPath"] != xpath
                            ]
                    except Exception as e:
                        print("st.session_state.selected_xpaths", st.session_state.selected_xpaths)
                        #print(e)
                    except (Exception) as e:
                        print("st.session_state.selected_xpaths", st.session_state.selected_xpaths)
        print("st.session_state.selected_xpaths_final", st.session_state.selected_xpaths)
        return st.session_state.selected_xpaths
    except (Exception) as e:
        return st.session_state.selected_xpaths
        print(e)

def adding_selected_xapth_excel(new_page_name,):
    for item in st.session_state.selected_xpaths:
        item['Page Name'] = new_page_name

    excel_file = xpath_file
    if os.path.exists(excel_file):
        # Read existing file
        existing_df = pd.read_excel(excel_file, engine='openpyxl')
    else:
        existing_df = pd.DataFrame()
    new_df = pd.DataFrame(st.session_state.selected_xpaths)
    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    combined_df = combined_df.drop_duplicates(subset=['XPath', 'Page Name'], keep='last')

    # Save the combined DataFrame back to the Excel file
    combined_df.to_excel(excel_file, index=False, engine='openpyxl')
    st.success(f"XPaths successfully added to Excel! Download the file [here](sandbox:{excel_file})")

def clean_xpath(xpath):
    """Extracts only the actual XPath from a given string."""
    match = re.search(r'(//[^\]]+\])', xpath)  # Find everything starting with // until the first ]
    return match.group(1) if match else xpath  # Return extracted XPath or original if not found

def generate_excel_testcases_with_document(prompt_type,extracted_data):
    prompt_template = load_prompt_from_file(prompt_type)
    # Conditionally inject Action Data section or leave it blank
    final_prompt = prompt_template.format(requirements=extracted_data)
    print(final_prompt)
    return final_prompt

def generate_testcase_accuracy_matrix(prompt_type,requirements,testcase):
    prompt_template = load_prompt_from_file(prompt_type)
    # Conditionally inject Action Data section or leave it blank
    final_prompt = prompt_template.format(requirement_text=requirements,test_case_text=testcase)
    print(final_prompt)
    return final_prompt

def generate_pom_from_excel_testcases(prompt_type,navigation,image_data,action_data=None,requirements=""):
    prompt_template = load_prompt_from_file(prompt_type)
    # Conditionally inject Action Data section or leave it blank
    if action_data:
        action_section = f"- User Interaction Elements (Action Data): {action_data}"
    else:
        action_section = ""
    final_prompt = prompt_template.format(navigation=navigation,image_data_processed=image_data,action_data_processed=action_section,requirements=requirements)
    print(final_prompt)
    return final_prompt

def generate_testcases_regeneration(prompt_type,navigation,image_data,action_data=None,requirements="",existing_prompt_response=None,accuracy_matrix=None):
    prompt_template = load_prompt_from_file(prompt_type)
    # Conditionally inject Action Data section or leave it blank
    if action_data:
        action_section = f"- User Interaction Elements (Action Data): {action_data}"
    else:
        action_section = ""
    final_prompt = prompt_template.format(navigation=navigation,image_data_processed=image_data,action_data_processed=action_section,requirements=requirements,accuracy_Details=accuracy_matrix,existing_prompt_response=existing_prompt_response)
    print(final_prompt)
    return final_prompt

def generate_testcases_regeneration_doc(prompt_type,requirements="",existing_prompt_response=None,accuracy_matrix=None,):
    prompt_template = load_prompt_from_file(prompt_type)
    # Conditionally inject Action Data section or leave it blank
    final_prompt = prompt_template.format(requirements=requirements,accuracy_Details=accuracy_matrix,existing_prompt_response=existing_prompt_response)
    print(final_prompt)
    return final_prompt

def generate_pom_from_excel_feature(prompt_type,Recorded_Action):
    prompt_template = load_prompt_from_file(prompt_type)
    final_prompt = prompt_template.format(recorded_action=Recorded_Action)
    print(final_prompt)
    return final_prompt

def generate_test_script(prompt_type,test_file_language,page_file_conetent,test_file_content,action_data=None):
    prompt_template = load_prompt_from_file(prompt_type)
    if action_data:
        final_prompt = prompt_template.format(
            test_file_language=test_file_language,
            page_files_content=page_file_conetent,
            test_files_content=test_file_content,
            recorded_actions=action_data
        )
    else:
        # Remove the optional section related to recorded_actions
        prompt_template = prompt_template.replace("3. (Optional) Recorded User Actions:\n{recorded_actions}\n\n", "")
        final_prompt = prompt_template.format(
            test_file_language=test_file_language,
            page_files_content=page_file_conetent,
            test_files_content=test_file_content,
            recorded_actions=""
        )

    print(final_prompt)
    return final_prompt

def generate_pom_from_excel_with_action(prompt_type,page_name,language,action_data):
    prompt_template = load_prompt_from_file(prompt_type)
    print(prompt_template)
    # Read Excel file
    excel_file = xpath_file
    if not os.path.exists(excel_file):
        print(f"Excel file not found: {excel_file}")
        return


    df = pd.read_excel(excel_file)

    # Check if required columns exist
    if not {"Element", "XPath", "Page Name"}.issubset(df.columns):
        print("Excel file is missing required columns: Element, XPath, Page Name")
        return

    # Filter XPaths based on Page Name
    filtered_df = df[df["Page Name"] == page_name]

    if filtered_df.empty:
        print(f"No elements found for page: {page_name}")
        return

    # Extract XPaths
    xpaths = "\n".join(filtered_df["XPath"].apply(clean_xpath).tolist())
    final_prompt = prompt_template.format(language=language,xpaths=xpaths,Action_data=action_data)
    print(final_prompt)
    return final_prompt

def generate_pom_from_excel(prompt_type,page_name,language):
    prompt_template = load_prompt_from_file(prompt_type)
    print(prompt_template)
    # Read Excel file
    excel_file = xpath_file
    if not os.path.exists(excel_file):
        print(f"Excel file not found: {excel_file}")
        return


    df = pd.read_excel(excel_file)

    # Check if required columns exist
    if not {"Element", "XPath", "Page Name"}.issubset(df.columns):
        print("Excel file is missing required columns: Element, XPath, Page Name")
        return

    # Filter XPaths based on Page Name
    filtered_df = df[df["Page Name"] == page_name]

    if filtered_df.empty:
        print(f"No elements found for page: {page_name}")
        return

    # Extract XPaths
    xpaths = "\n".join(filtered_df["XPath"].apply(clean_xpath).tolist())

    final_prompt = prompt_template.format(language=language,xpaths=xpaths)
    print(final_prompt)
    return final_prompt

def scroll_and_focus():
    st.markdown("""
        <script>
        setTimeout(function() {
            const topElement = document.querySelector("a[name='top-button']");
            if (topElement) {
                topElement.scrollIntoView({ behavior: "smooth" });
            }
            const buttons = Array.from(document.querySelectorAll('button'));
            const collectButton = buttons.find(btn => btn.innerText.trim() === 'Collecting Elements');
            if (collectButton) {
                collectButton.focus();
            }
        }, 500);
        </script>
    """, unsafe_allow_html=True)

def select_and_read_text_files(folder_path):
    # Step 1: List all .txt files in the folder
    txt_files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]

    if not txt_files:
        st.warning("No .txt files found in the folder.")
        return {}

    # Step 2: Let the user select multiple files
    selected_files = st.multiselect("Select relevant file(s)", txt_files)

    # Step 3: Read contents of selected files
    file_contents = {}
    for file_name in selected_files:
        full_path = os.path.join(folder_path, file_name)
        with open(full_path, 'r', encoding='utf-8') as f:
            file_contents[file_name] = f.read()

    # Step 4: Return dictionary of filename: content
    return file_contents
def get_window_statuses(driver):
    try:
        return driver.execute_script("""
            const results = {};
            for (let i=0; i<localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key.startsWith("recorder_status_")) {
                    try {
                        const data = JSON.parse(localStorage.getItem(key));
                        if (data && data.windowId) {
                            results[data.windowId] = data;  // use clean windowId as key
                        }
                    } catch (e) {
                        console.warn("⚠️ Bad status JSON for", key, e);
                    }
                }
            }
            return results;
        """)
    except Exception:
        return {}



def thread_new_window_checker(driver, injected_windows, last_urls, stop_flag, screenshot_folder, current_window_ref):
    """
    Monitor newly opened windows and inject JS.
    """
    print("thread 1 started")
    while not stop_flag["stop"]:
        try:
            handles = driver.window_handles
            for handle in handles:
                if handle not in injected_windows:
                    # New window detected
                    driver.switch_to.window(handle)
                    driver.execute_script(action_utils.injection_script_updated_fixed())

                    # Mark as injected
                    injected_windows[handle] = True
                    last_urls[handle] = driver.current_url
                    current_window_ref["handle"] = handle

                    print(f"✅ JS injected in new window {handle} ({driver.current_url})")
                    # Optionally: take screenshot
                    # _take_screenshot(driver, driver.current_url, screenshot_folder)
            print("thread 1 ended")
        except Exception as e:
            print("New window monitor error:", e)

        # Check every 2-3 seconds
        time.sleep(3)

def thread_focus_screenshot(driver,stop_flag,screenshot_folder,source="file"):
    """
    Screenshots
    """
    print("screenshot thread started")
    last_url = ""
    while not stop_flag["stop"]:
        try:
            current_url = driver.current_url
            if current_url != last_url:
                last_url = current_url

                # Wait for page to fully load
                for _ in range(50):  # up to ~5 seconds
                    state = driver.execute_script("return document.readyState")
                    if state == "complete":
                        break
                    time.sleep(0.1)

                # Then take screenshot as before
                if source == "file":
                    filepath = action_utils.take_screenshot(driver, screenshot_folder)
                elif source == "database":
                    filepath = db_handler.take_screenshot_db(driver, "sathanantham")
                else:
                    filepath = None
                print(f"📸 Screenshot taken for: {current_url} => {filepath}")
                print("screenshot thread ended")
        except Exception as e:
            print("Error during URL monitoring:", e)
        time.sleep(1)  # check every second
import time
from datetime import datetime

# def thread_reinject_action_check(driver, stop_flag,
#                                  last_urls=None, current_window_ref=None,
#                                  injected_windows=None, idle_timeout=5):
#     """
#     Reinjection checker thread:
#     - Monitors last action timestamp and action count in localStorage
#     - Clears injected_windows only if:
#         1. Idle time exceeded > idle_timeout
#         2. New actions were recorded since last reinject
#     - Updates last_action_ts after reinjection to prevent unnecessary clears
#     """
#     print("🧵 thread 3 started (idle reinject checker)")
#
#     # Track last known action count
#     last_action_count = 0
#
#     while not stop_flag["stop"]:
#         try:
#             # Fetch from localStorage
#             result = driver.execute_script("""
#                 const actions = JSON.parse(localStorage.getItem('recordedActions') || '[]');
#                 const lastReinject = localStorage.getItem('lastReinjectTime');
#                 let lastActionTs = null;
#
#                 if (actions.length > 0) {
#                     lastActionTs = actions[actions.length - 1].timestamp || null;
#                 }
#
#                 return {
#                     lastAction: lastActionTs,
#                     lastReinject: lastReinject,
#                     actionCount: actions.length
#                 };
#             """)
#
#             last_action = result.get("lastAction")
#             last_reinject = result.get("lastReinject")
#             action_count = result.get("actionCount", 0)
#
#             # Parse last action timestamp
#             last_action_ts = None
#             if last_action:
#                 if isinstance(last_action, (int, float)):  # epoch millis
#                     last_action_ts = float(last_action) / 1000.0
#                 elif isinstance(last_action, str):
#                     try:
#                         dt = datetime.fromisoformat(last_action.replace("Z", "+00:00"))
#                         last_action_ts = dt.timestamp()
#                     except Exception as parse_err:
#                         print(f"⚠️ Could not parse ISO timestamp: {last_action} ({parse_err})")
#
#             # Parse reinjection timestamp
#             last_reinject_ts = None
#             if last_reinject:
#                 try:
#                     last_reinject_ts = float(last_reinject)
#                 except:
#                     pass
#
#             if last_action_ts:
#                 now_ts = time.time()
#                 diff = now_ts - last_action_ts
#
#                 print("⏰ Current Time:", datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d %H:%M:%S"))
#                 print("📝 Last Action:", datetime.fromtimestamp(last_action_ts).strftime("%Y-%m-%d %H:%M:%S"))
#                 if last_reinject_ts:
#                     print("♻️ Last Reinjection:", datetime.fromtimestamp(last_reinject_ts).strftime("%Y-%m-%d %H:%M:%S"))
#                 print("🔢 Action Count:", action_count)
#
#                 # ✅ MAIN CHECK: only reinject if new actions appeared after last reinject
#                 if (not last_reinject_ts or last_action_ts > last_reinject_ts):
#                     idle_condition = diff >= idle_timeout
#                     new_actions_condition = action_count > last_action_count
#
#                     if idle_condition and new_actions_condition:
#                         print(f"⏱️ Idle > {idle_timeout}s AND new actions detected. Clearing injected_windows…")
#                         if injected_windows is not None:
#                             injected_windows.clear()
#
#                         # Update reinjection time + last action time
#                         driver.execute_script("""
#                             localStorage.setItem('lastReinjectTime', Date.now() / 1000);
#                         """)
#                         last_action_ts = now_ts
#                         last_action_count = action_count  # reset count reference
#
#                         time.sleep(1)
#
#             else:
#                 print("ℹ️ No actions recorded yet.")
#
#         except Exception as e:
#             print("Idle reinject monitor error:", e)
#
#         time.sleep(2)
#
#     print("🛑 thread 3 stopped (idle reinject checker)")

def thread_reinject_action_check(driver, stop_flag,
                                 last_urls=None, current_window_ref=None,
                                 injected_windows=None, idle_timeout=5):
    """
    Reinjection when no action for > idle_timeout seconds.
    Handles both epoch-ms and ISO 8601 timestamps.
    Tracks last reinjection time in localStorage so reinjection
    only happens if a new action occurred after the last reinject.
    """
    print("🧵 thread 3 started (idle reinject checker)")

    while not stop_flag["stop"]:
        try:
            # Get last recorded action and last reinjection time from localStorage
            result = driver.execute_script("""
                const actions = JSON.parse(localStorage.getItem('recordedActions') || '[]');
                const lastReinject = localStorage.getItem('lastReinjectTime');
                let lastActionTs = null;

                if (actions.length > 0) {
                    lastActionTs = actions[actions.length - 1].timestamp || null;
                }

                return {
                    lastAction: lastActionTs,
                    lastReinject: lastReinject
                };
            """)

            last_action = result.get("lastAction")
            last_reinject = result.get("lastReinject")

            # Convert action timestamp
            last_action_ts = None
            if last_action:
                if isinstance(last_action, (int, float)):  # epoch millis
                    last_action_ts = float(last_action) / 1000.0
                elif isinstance(last_action, str):
                    try:
                        dt = datetime.fromisoformat(last_action.replace("Z", "+00:00"))
                        last_action_ts = dt.timestamp()
                    except Exception as parse_err:
                        print(f"⚠️ Could not parse ISO timestamp: {last_action} ({parse_err})")

            # Convert reinjection timestamp
            last_reinject_ts = None
            if last_reinject:
                try:
                    last_reinject_ts = float(last_reinject)
                except:
                    pass

            if last_action_ts:
                now_ts = time.time()
                print("⏰ Current Time:", datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d %H:%M:%S"))
                print("📝 Last Action:", datetime.fromtimestamp(last_action_ts).strftime("%Y-%m-%d %H:%M:%S"))
                if last_reinject_ts:
                    print("♻️ Last Reinjection:", datetime.fromtimestamp(last_reinject_ts).strftime("%Y-%m-%d %H:%M:%S"))

                # ✅ MAIN CHECK: Only if new action happened after last reinject
                if not last_reinject_ts or last_action_ts > last_reinject_ts:
                    diff = now_ts - last_action_ts
                    print("🔎 Difference (sec):", round(diff, 2))

                    if diff >= idle_timeout:  # ⬅️ MAIN idle timeout check
                        print(f"⏱️ Idle > {idle_timeout}s detected. Clearing injected_windows…")
                        if injected_windows is not None:
                            injected_windows.clear()

                        # Update reinjection time
                        driver.execute_script("""
                            localStorage.setItem('lastReinjectTime', Date.now() / 1000);
                        """)
                        time.sleep(1)

            else:
                print("ℹ️ No actions recorded yet.")

        except Exception as e:
            print("Idle reinject monitor error:", e)

        time.sleep(2)

    print("🛑 thread 3 stopped (idle reinject checker)")

def thread_focus_and_url_monitor(driver, injected_windows, last_urls, stop_flag, screenshot_folder, current_window_ref):
    """
    Monitor the current window for focus or URL changes. Reinjection if DOM replaced.
    """
    print("thread 2 started")

    while not stop_flag["stop"]:
        try:
            # Always read the last focused window
            last_focused = driver.execute_script("return localStorage.getItem('lastFocusedWindow');")
            print("last_focused------",last_focused)
            current_handle = driver.current_window_handle
            current_window_ref["handle"] = current_handle
            print("current_window_ref------", current_window_ref["handle"])
            current_url = driver.current_url
            print("current_url------", current_url)
            print("last url-----",last_urls.get(current_handle))

            # Compare last URL for current handle
            print("last_urls.get(current_handle)",last_urls.get(current_handle))
            if last_urls.get(current_handle) != current_url:
                driver.execute_script(action_utils.injection_script_updated_fixed())
                last_urls[current_handle] = current_url
                print(f"🔄 URL changed in window {current_handle}, JS reinjected ({current_url})")

            # # Check if another window has focus
            # if last_focused and last_focused != current_handle:
            #     if last_focused in injected_windows:
            #         # Optionally, inject JS without switching focus
            #         driver.switch_to.window(last_focused)
            #         focused_url = driver.current_url
            #         if last_urls.get(last_focused) != focused_url:
            #             driver.execute_script(action_utils.injection_script_updated_fixed())
            #             last_urls[last_focused] = focused_url
            #             print(f"🔄 Focused window changed, JS reinjected in {last_focused} ({focused_url})")
            #         driver.switch_to.window(current_handle)  # return focus to current window

        except Exception as e:
            print("Focus/URL monitor error:", e)

        time.sleep(2)

def monitor_url_changes_for_each_nav_old(driver, screenshot_folder, stop_flag):
    last_url = ""
    while not stop_flag["stop"]:
        try:
            current_url = driver.current_url
            if current_url != last_url:
                last_url = current_url

                # Wait for page to fully load
                for _ in range(50):  # up to ~5 seconds
                    state = driver.execute_script("return document.readyState")
                    if state == "complete":
                        break
                    time.sleep(0.1)

                # Re-inject your recorder JS here
                action_utils.start_recording(driver)  # Make sure injection_script1 is in scope!

                # Then take screenshot as before
                if source == "file":
                    filepath = action_utils.take_screenshot(driver, screenshot_folder)
                elif source == "database":
                    filepath = db_handler.take_screenshot_db(driver, "sathanantham")
                else:
                    filepath = None
                print(f"📸 Screenshot taken for: {current_url} => {filepath}")

        except Exception as e:
            print("Error during URL monitoring:", e)
        time.sleep(1)  # check every second

def select_and_read_text_files_xpath(type, folder_path):
    # Step 1: List all files in the folder
    files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]

    if not files:
        st.warning("No files found in the folder.")
        return {}

    selected_files = st.multiselect(f"Select relevant file(s) for {type.replace('_', ' ')}", files)

    file_contents = {}

    for file_name in selected_files:
        full_path = os.path.join(folder_path, file_name)

        try:
            # Type: For txt-based files
            if type in ["xpath","recorded action (Optional)", "page", "feature"]:
                with open(full_path, 'r', encoding='utf-8') as f:
                    file_contents[file_name] = f.read()

            elif type in ("page_test", "pom_file","test_file") and file_name.endswith((".py", ".java", ".cs", ".js")):
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Remove common Markdown wrappers
                    for lang in ["python", "java", "csharp", "javascript"]:
                        if content.startswith(f"```{lang}"):
                            content = content.split(f"```{lang}", 1)[1]
                            break  # remove only one matching wrapper
                    if "```" in content:
                        content = content.split("```", 1)[0]

                    file_extension = os.path.splitext(file_name)[1].lower()

                    # Process based on file type
                    if file_extension == ".py":
                        try:
                            tree = ast.parse(content)
                            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
                            file_contents[file_name] = functions
                        except SyntaxError as syntax_err:
                            st.error(
                                f"Syntax error in {file_name}:\nLine {syntax_err.lineno} - {syntax_err.text.strip() if syntax_err.text else ''}")
                            continue

                    else:
                        # For Java, C#, JS – just collect method/function-like definitions as lines (basic version)
                        lines = content.splitlines()
                        func_like_lines = []
                        for line in lines:
                            line_strip = line.strip()
                            # crude method detection for other languages
                            if file_extension == ".java" and (" void " in line_strip or line_strip.endswith(");")):
                                func_like_lines.append(line_strip)
                            elif file_extension == ".cs" and (
                                    " void " in line_strip or "public" in line_strip or "private" in line_strip):
                                func_like_lines.append(line_strip)
                            elif file_extension == ".js" and ("function " in line_strip or "=>" in line_strip):
                                func_like_lines.append(line_strip)
                        file_contents[file_name] = func_like_lines

                except Exception as read_err:
                    st.error(f"Failed to read {file_name}: {read_err}")

            # Type: For Excel test cases - testcase_test
            elif type == "testcase_test" and file_name.endswith((".xlsx", ".xls")):
                df = pd.read_excel(full_path)

                test_case_name = df['Test Case Name'][0]
                page_name = df['Page'][0] if 'Page' in df.columns else None
                actions = df['Action'].dropna().tolist() if 'Action' in df.columns else []
                expected = df['Expected Result'].dropna().tolist() if 'Expected Result' in df.columns else []

                file_contents[file_name] = {
                    "test_case_name": test_case_name,
                    "page_name": page_name,
                    "actions": actions,
                    "expected_results": expected
                }

            else:
                st.warning(f"Unsupported or mismatched file type for {file_name}")

        except Exception as e:
            st.error(f"Error processing {file_name}: {e}")

    return file_contents

import re

import re


def parse_testcases_from_markdown(md_text):
    """
    Parse a Markdown table into structured test case dicts.
    Handles multi-line cells and extra pipes in descriptions.
    Returns a list of dicts, each with test case name, step number, description, expected, status, type.
    """
    rows = []
    md_text = md_text.strip()

    # Remove header/separator lines
    lines = [line for line in md_text.splitlines() if line.strip() and not re.match(r'^\|\s*-', line)]

    # Collect multi-line rows
    buffer = ""
    for line in lines:
        if line.startswith("|"):
            buffer += line + "\n"
            # Count pipes in the line; a full row should have 7 '|' for 6 columns
            if buffer.count("|") >= 7:
                # Extract cells safely, even if pipes appear in text
                parts = re.split(r'\s*\|\s*', buffer.strip())
                parts = [p.strip() for p in parts[1:-1]]  # skip first and last empty split
                if len(parts) == 6:
                    rows.append({
                        "name": parts[0],
                        "step_number": parts[1],
                        "description": parts[2],
                        "expected": parts[3],
                        "status": parts[4],
                        "type": parts[5],
                    })
                buffer = ""  # reset for next row
    return rows


def build_markdown_table(testcases):
    """
    Build a Markdown table from a list of test case dicts.
    Groups by test case name automatically.
    """
    header = "| Test Case Name | Step Number | Test Step Description | Test Step Expected Result | Status | Type |\n"
    header += "|----------------|-------------|-----------------------|---------------------------|--------|------|\n"

    body = ""
    for case in testcases:
        body += f"| {case['name']} | {case['step_number']} | {case['description']} | {case['expected']} | {case['status']} | {case['type']} |\n"

    return header + body

def generate_testcases_with_retries(constructed_prompt, retries=3, target_count=20):
    all_testcase_output=[]
    all_testcases = []
    seen_steps = set()
    all_raw_responses = ""

    for i in range(retries):
        print(f"***********Iteration {i}*****************")

        # Build exclusion text for already generated cases
        if all_testcases:
            existing_names = set(c["name"] for c in all_testcases)
            exclusion_text = (
                "Already generated test cases:\n" + "\n".join(existing_names) +
                "\nNow generate NEW test cases not in the above list. Continue numbering."
            )
            prompt = constructed_prompt + "\n\n" + exclusion_text
        else:
            prompt = constructed_prompt

        # Call LLM
        response = get_queries_from_ai_updated(prompt)
        all_raw_responses += "\n" + response
        all_testcase_output.append(response)
        # Parse Markdown rows robustly
        new_cases = parse_testcases_from_markdown(response)
        for case in new_cases:
            step_key = (case["name"], case["step_number"])
            if step_key not in seen_steps:
                seen_steps.add(step_key)
                all_testcases.append(case)

        if len(set(c["name"] for c in all_testcases)) >= target_count:
            break

    # Build Markdown table from all collected steps
    #return build_markdown_table(all_testcases)
    return all_testcase_output



def get_queries_from_ai_updated_again(formatted_summary, previous_output):
    # Access the variables
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

    # Set the environment variables explicitly if needed
    os.environ["AZURE_OPENAI_API_KEY"] = api_key
    os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint

    model = AzureChatOpenAI(
        openai_api_version="2023-05-15",
        azure_deployment="qepracticekey",
        max_tokens=4000,  # adjust depending on your model quota
        temperature=0
    )
    prompt=formatted_summary+"please review the below output and don't generate test cases for those scenarios /n"+previous_output
    message = HumanMessage(content=prompt)
    output_value = model([message])
    print(output_value)
    return output_value.content
def get_queries_from_ai_updated(formatted_summary):
    # Access the variables
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

    # Set the environment variables explicitly if needed
    os.environ["AZURE_OPENAI_API_KEY"] = api_key
    os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint

    model = AzureChatOpenAI(
        openai_api_version="2023-05-15",
        azure_deployment="qepracticekey",
        max_tokens=4000,  # adjust depending on your model quota
        temperature=0
    )
    message = HumanMessage(content=formatted_summary)
    output_value = model([message])
    print(output_value)
    return output_value.content

def markdown_to_dataframe(markdown_text):
    # Extract lines that look like markdown rows
    lines = markdown_text.strip().splitlines()
    table_lines = [line for line in lines if "|" in line and not line.strip().startswith("---")]

    if len(table_lines) < 2:
        print("⚠️ No valid markdown table found.")
        return pd.DataFrame()

    # Clean up each line
    cleaned_lines = [re.sub(r"^\s*\|\s*|\s*\|\s*$", "", line).strip() for line in table_lines]
    cleaned_lines = [re.sub(r"\s*\|\s*", ",", line) for line in cleaned_lines]

    csv_data = "\n".join(cleaned_lines)

    print("🔍 Cleaned CSV-like content:\n", csv_data)

    # Use StringIO to load into DataFrame
    try:
        df = pd.read_csv(StringIO(csv_data))
        return df
    except Exception as e:
        print(f"❌ Failed to convert markdown to DataFrame: {e}")
        return pd.DataFrame()
# def covert_response_to_testcases(markdown_text,test_collection):
#     # STEP 1: Strip markdown code fencing (``` or ```markdown)
#     if markdown_text.startswith("```"):
#         markdown_text = "\n".join(
#             line for line in markdown_text.splitlines()
#             if not line.strip().startswith("```")
#         )
#     # STEP 2: Clean and parse markdown table
#     lines = markdown_text.strip().split('\n')
#     cleaned_lines = [line for line in lines if not set(line.strip()).issubset(set('|- '))]
#     cleaned_text = "\n".join(cleaned_lines)
#
#     df = pd.read_csv(StringIO(cleaned_text), sep='|', engine='python')
#     df = df.dropna(axis=1, how='all')
#     df.columns = [col.strip() for col in df.columns]
#     # df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
#     for col in df.select_dtypes(include='object').columns:
#         df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)
#
#     # STEP 3: Fill missing Test Case Names
#     df['Test Case Name'] = df['Test Case Name'].replace('', pd.NA).ffill()
#
#
#     # STEP 5: Write each test case into a separate Excel file
#     for test_case, group in df.groupby("Test Case Name"):
#         file_name = f"{test_case.strip()[:50]}.xlsx"  # Truncate for safety
#         safe_file_name = "".join(c for c in file_name if c.isalnum() or c in "._- ()").rstrip()
#         path = os.path.join(test_collection, safe_file_name)
#         group.to_excel(path, index=False)
#
#     print(f"✅ Created individual Excel files in folder: {output_folder}")

def clean_table_lines(raw_markdown):
    cleaned_lines = []
    for line in raw_markdown.strip().splitlines():
        line = line.strip()
        if "|" in line and not set(line).issubset(set("|- ")) and line.count("|") >= 3:
            cleaned_lines.append(line.strip("|").strip())  # Remove leading/trailing pipes
    return cleaned_lines

def covert_response_to_testcases(markdown_text, test_collection):
    print("\n🚀 Starting test case parsing...")

    if source == "file":
        if not os.path.exists(test_collection):
            os.makedirs(test_collection)
            print(f"📁 Created output directory: {test_collection}")
    if isinstance(markdown_text, list):
        markdown_text = "\n".join(str(line) for line in markdown_text)

    elif not isinstance(markdown_text, str):
        markdown_text = str(markdown_text)
    if markdown_text.startswith("```"):
        markdown_text = "\n".join(
            line for line in markdown_text.splitlines()
            if not line.strip().startswith("```")
        )

    # Fix 1: Clean up AI-format table lines
    table_lines = clean_table_lines(markdown_text)

    if len(table_lines) >= 2 and "Test Case Name" in table_lines[0]:
        table_text = "\n".join(table_lines)
        try:
            df = pd.read_csv(StringIO(table_text), sep='|', engine='python', on_bad_lines='skip')
            df = df.dropna(axis=1, how='all')
            df.columns = [re.sub(r'\*+', '', col.strip()) for col in df.columns]
            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

            if 'Test Case Name' not in df.columns:
                raise ValueError("'Test Case Name' column missing.")

            df['Test Case Name'] = df['Test Case Name'].replace('', pd.NA).ffill()

            for test_case, group in df.groupby('Test Case Name'):
                file_name = f"{test_case.strip()[:50]}.xlsx"
                safe_file_name = "".join(c for c in file_name if c.isalnum() or c in "._- ()").rstrip()

                if source == "file":
                    path = os.path.join(test_collection, safe_file_name)
                    group.to_excel(path, index=False)
                    print(f"✅ Saved to file: {safe_file_name}")
                elif source == "database":
                    #content_str = group.to_csv(index=False)
                    db_handler.save_testcases_to_db(safe_file_name, group, "sathanantham")
                    #db_handler.save_testcases_to_db(safe_file_name[:50], content_str, "sathanantham")
                    print(f"✅ Saved to DB: {safe_file_name}")

            print(f"\n✅ Successfully saved {df['Test Case Name'].nunique()} test case files.")
            st.write(f"\n✅ Successfully saved {df['Test Case Name'].nunique()} test case files.")
            return

        except Exception as e:
            print(f"❌ Failed to parse single-table format: {e}")
            print("🔁 Attempting markdown section fallback...")

    # STEP 2: Fallback to splitting by markdown sections
    test_cases = re.split(r'####\s+\*\*(.*?)\*\*', markdown_text)
    if len(test_cases) < 3:
        print("❌ No valid markdown headings found either. Exiting.")
        return

    for i in range(1, len(test_cases), 2):
        test_case_name = test_cases[i].strip()
        test_case_body = test_cases[i + 1]

        lines = []
        for line in test_case_body.strip().splitlines():
            line = line.strip()
            if "|" in line and not set(line).issubset(set("|- ")):
                lines.append(line)

        if not lines:
            print(f"⚠️ No valid table in: {test_case_name}")
            continue

        table_text = "\n".join(lines)

        try:
            df = pd.read_csv(StringIO(table_text), sep='|', engine='python')
            df = df.dropna(axis=1, how='all')
            df.columns = [re.sub(r'\*+', '', col.strip()) for col in df.columns]

            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

            if 'Test Case Name' not in df.columns:
                df.insert(0, 'Test Case Name', test_case_name)
            else:
                df['Test Case Name'] = df['Test Case Name'].replace('', pd.NA).ffill()
            for test_case, group in df.groupby('Test Case Name'):
                safe_file_name = "".join(c for c in test_case[:50] if c.isalnum() or c in "._- ()").rstrip()

                if source == "file":
                    path = os.path.join(test_collection, safe_file_name + ".xlsx")
                    group.to_excel(path, index=False)
                    print(f"✅ Saved to file: {safe_file_name}")
                elif source == "database":
                    #content_str = group.to_csv(index=False)
                    db_handler.save_testcases_to_db(safe_file_name, group, "sathanantham")
                    #db_handler.save_testcases_to_db(safe_file_name, content_str, "sathanantham")
                    print(f"✅ Saved to DB: {safe_file_name}")

        except Exception as e:
            print(f"❌ Failed to parse section: {test_case_name}")
            print(f"   Error: {e}")

    if source == "file":
        print(f"\n✅ Completed saving all test cases to folder: {test_collection}")
        st.write(f"\n✅ Completed saving all test cases to folder: {test_collection}")
    elif source == "database":
        print(f"\n✅ Completed saving all test cases to the database.")
        st.write(f"\n✅ Completed saving all test cases to the database.")

def covert_response_to_testcases_1(markdown_text, test_collection):
    print("\n🚀 Starting test case parsing...")

    # Ensure output directory exists
    if not os.path.exists(test_collection):
        os.makedirs(test_collection)
        print(f"📁 Created output directory: {test_collection}")

    # Remove markdown code fences
    if markdown_text.startswith("```"):
        markdown_text = "\n".join(
            line for line in markdown_text.splitlines()
            if not line.strip().startswith("```")
        )

    # STEP 1: Try to detect if it's a big single table
    table_lines = []
    for line in markdown_text.strip().splitlines():
        line = line.strip()
        if "|" in line and not set(line).issubset(set("|- ")):
            table_lines.append(line)

    if len(table_lines) >= 2 and "Test Case Name" in table_lines[0]:
        # Likely a single big table
        table_text = "\n".join(table_lines)
        try:
            df = pd.read_csv(StringIO(table_text), sep='|', engine='python')
            df = df.dropna(axis=1, how='all')
            # df.columns = [col.strip() for col in df.columns]
            df.columns = [re.sub(r'\*+', '', col.strip()) for col in df.columns]
            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

            # Validate 'Test Case Name'
            if 'Test Case Name' not in df.columns:
                raise ValueError("'Test Case Name' column missing.")

            df['Test Case Name'] = df['Test Case Name'].replace('', pd.NA).ffill()

            # Group by 'Test Case Name'
            for test_case, group in df.groupby('Test Case Name'):
                file_name = f"{test_case.strip()[:50]}.xlsx"
                safe_file_name = "".join(c for c in file_name if c.isalnum() or c in "._- ()").rstrip()
                # path = os.path.join(test_collection, safe_file_name)
                # group.to_excel(path, index=False)
                # print(f"✅ Saved: {safe_file_name}")
                if source == "file":
                    path = os.path.join(test_collection, safe_file_name)
                    df.to_excel(path, index=False)
                    print(f"✅ Saved to file: {safe_file_name}")
                elif source == "database":
                    #content_str = df.to_csv(index=False)
                    content_str = group.to_csv(index=False)
                    db_handler.save_testcases_to_db(safe_file_name[:50], content_str, "sathanantham")
                    print(f"✅ Saved to DB: {safe_file_name}")

            print(f"\n✅ Successfully saved {df['Test Case Name'].nunique()} test case files.")
            return

        except Exception as e:
            print(f"❌ Failed to parse single-table format: {e}")
            print("🔁 Attempting markdown section fallback...")

    # STEP 2: Fallback to splitting by markdown sections (#### **Test Case Name**)
    test_cases = re.split(r'####\s+\*\*(.*?)\*\*', markdown_text)
    if len(test_cases) < 3:
        print("❌ No valid markdown headings found either. Exiting.")
        return

    for i in range(1, len(test_cases), 2):
        test_case_name = test_cases[i].strip()
        test_case_body = test_cases[i + 1]

        lines = []
        for line in test_case_body.strip().splitlines():
            line = line.strip()
            if "|" in line and not set(line).issubset(set("|- ")):
                lines.append(line)

        if not lines:
            print(f"⚠️ No valid table in: {test_case_name}")
            continue

        table_text = "\n".join(lines)

        try:
            df = pd.read_csv(StringIO(table_text), sep='|', engine='python')
            df = df.dropna(axis=1, how='all')
            # df.columns = [col.strip() for col in df.columns]
            df.columns = [re.sub(r'\*+', '', col.strip()) for col in df.columns]

            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

            if 'Test Case Name' not in df.columns:
                df.insert(0, 'Test Case Name', test_case_name)
            else:
                df['Test Case Name'] = df['Test Case Name'].replace('', pd.NA).ffill()

            file_name = f"{test_case_name.strip()[:50]}.xlsx"
            safe_file_name = "".join(c for c in file_name if c.isalnum() or c in "._- ()").rstrip()
            # path = os.path.join(test_collection, safe_file_name)
            # df.to_excel(path, index=False)
            # print(f"✅ Saved: {safe_file_name}")
            if source == "file":
                path = os.path.join(test_collection, safe_file_name)
                df.to_excel(path, index=False)
                print(f"✅ Saved to file: {safe_file_name}")
            elif source == "database":
                #content_str = df.to_csv(index=False)
                content_str = group.to_csv(index=False)
                db_handler.save_testcases_to_db(test_case_name[:50], content_str, "sathanantham")
                print(f"✅ Saved to DB: {test_case_name}")

        except Exception as e:
            print(f"❌ Failed to parse section: {test_case_name}")
            print(f"   Error: {e}")

    print(f"\n✅ Completed saving all test cases to: {test_collection}")

def create_testcase_in_Excel(raw_response, test_location):
    os.makedirs(test_location, exist_ok=True)

    df = markdown_to_dataframe(raw_response)

    if df.empty:
        print("⚠️ No test cases found in the markdown.")
        return

    print("✅ Parsed DataFrame:\n", df)

    for name, group in df.groupby("Test Case Name"):
        safe_name = name.replace(" ", "_").replace("/", "_").strip()
        file_path = os.path.join(test_location, f"{safe_name}.xlsx")
        group.to_excel(file_path, index=False)

    print(f"✅ {len(df['Test Case Name'].unique())} test cases saved in: {test_location}")

import io
def extract_testcase_context_from_excel_file(file_obj):
    try:
        # If it's a string (file path), let pandas handle it
        if isinstance(file_obj, str):
            df = pd.read_excel(file_obj)

        # If it's a file-like object (e.g., from Streamlit), decode to BytesIO
        else:
            file_bytes = file_obj.read()
            df = pd.read_excel(io.BytesIO(file_bytes))

        test_case_name = df['Test Case Name'][0]
        page_name = df['Page'][0] if 'Page' in df.columns else None
        actions = df['Action'].dropna().tolist() if 'Action' in df.columns else []
        expected = df['Expected Result'].dropna().tolist() if 'Expected Result' in df.columns else []

        return {
            "test_case_name": test_case_name,
            "page_name": page_name,
            "actions": actions,
            "expected_results": expected
        }

    except Exception as e:
        print(f"❌ Error extracting test case context: {e}")
        return {
            "test_case_name": "",
            "page_name": "",
            "actions": [],
            "expected_results": []
        }

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def extract_text_from_pdf(uploaded_pdf):
    text = ""
    pdf_reader = PyPDF2.PdfReader(uploaded_pdf)
    num_pages = len(pdf_reader.pages)
    for page_number in range(num_pages):
        page = pdf_reader.pages[page_number]
        # Extract text and remove non-alphanumeric characters
        text += re.sub(r'\W+', ' ', page.extract_text())
    print("text extracted"+text)
    return text


def extract_text_from_document(uploaded_file, filename):
    text = ""

    if filename.lower().endswith(".pdf"):
        # PDF Extraction
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        for page in pdf_reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += re.sub(r'\W+', ' ', extracted)

    elif filename.lower().endswith(".docx"):
        # Word Document Extraction
        text_content = docx2txt.process(uploaded_file)
        text += re.sub(r'\W+', ' ', text_content)

    elif filename.lower().endswith(".txt"):
        # Plain Text File Extraction
        text_content = uploaded_file.read().decode("utf-8", errors="ignore")
        text += re.sub(r'\W+', ' ', text_content)

    else:
        raise ValueError("Unsupported file type. Only PDF, DOCX, and TXT are supported.")

    print("✅ Text extracted:", text)
    return text


def get_queries_from_ai_file_extract(uploaded_pdf):
    os.environ["AZURE_OPENAI_API_KEY"] = "4fed2bedb59744a99b0424622f6d9d1b"
    os.environ["AZURE_OPENAI_ENDPOINT"] = "https://qepracticekey.openai.azure.com/"
    extracted_text = extract_text_from_pdf(uploaded_pdf)

    val2 = """
Act as Functional Test Case Generator. Based on a given Requirement, create detailed and comprehensive test cases using the Orthogonal Array technique. Each test case should have multiple steps, covering a sequence of actions to verify functionality. Use the following columns in the output Excel sheet: 
- Test Case Name
- Step Number
- Test Step Description
- Test Step Expected Result
- Status (set as 'New')
- Type (set as 'Manual') 

Ensure that each test case contains:
- Multiple detailed steps with clear descriptions of actions to perform.
- Expected results for each step, specifying the criteria for a successful outcome.
- Coverage of both Positive and Negative scenarios, highlighting edge cases and valid/invalid inputs.
- Sequential numbering of steps, ensuring clarity in the flow of operations.
- The final test cases should verify all combinations of parameters from the Orthogonal Array, ensuring exhaustive coverage of pairwise interactions.

Format:
-Table

Include examples where applicable.
Create the test cases in the similar format with the following requirement:
""" + extracted_text[:8000]

    model = AzureChatOpenAI(
        openai_api_version="2023-05-15",
        azure_deployment="qepracticekey",
    )
    message = HumanMessage(
        content=val2
    )
    output_value = model([message])
    return (output_value.content)


def extract_page_file_info_from_file(file_obj):
    try:
        # Read actual content of the file
        content = file_obj.read().decode('utf-8')  # decode if it's a file-like object from Streamlit

        # Parse the code content, not the file name
        tree = ast.parse(content)

        methods = []
        xpaths = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                methods.append(node.name)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                        val_str = ast.unparse(node.value)
                        if "xpath" in val_str.lower():
                            xpaths.append((target.id, val_str))

        return {
            "methods": methods,
            "xpaths": xpaths
        }

    except Exception as e:
        print(f"Error parsing file: {e}")
        return {
            "methods": [],
            "xpaths": []
        }


def push_file_to_github(file_path, file_content, repo, branch):
    try:
        existing = repo.get_contents(file_path, ref=branch)
        repo.update_file(
            path=file_path,
            message=f"Update {file_path}",
            content=str(file_content),
            sha=existing.sha,
            branch=branch
        )
        st.success(f"✅ Updated: `{file_path}`")
    # except GithubException as e:
    #     if e.status == 404:
    except gitlab.GitlabGetError as e:
        if e.response_code == 404:
            # File doesn't exist – create it
            repo.create_file(
                path=file_path,
                message=f"Upload {file_path}",
                content=str(file_content),
                branch=branch
            )
            st.success(f"🆕 Created: `{file_path}`")
        else:
            st.error(f"❌ Error for `{file_path}`: {e.data['message']}")


def push_file_to_gitlab(file_path, file_content, repo, branch):
    try:
        # Check if file already exists in GitLab
        file = repo.files.get(file_path=file_path, ref=branch)

        # File exists — update it
        file.content = str(file_content)
        file.save(branch=branch, commit_message=f"Update {file_path}")
        st.success(f"✅ Updated: `{file_path}`")

    except gitlab.exceptions.GitlabGetError as e:
        if e.response_code == 404:
            # File doesn't exist — create it
            repo.files.create({
                'file_path': file_path,
                'branch': branch,
                'content': str(file_content),
                'commit_message': f"Upload {file_path}"
            })
            st.success(f"🆕 Created: `{file_path}`")
        else:
            st.error(f"❌ GitLab error for `{file_path}`: {e.error_message}")


def deduplicate_element_records(elements):
    seen = set()
    deduped = []
    for el in elements:
        # Pick a unique identifier
        unique_key = el.get("id") or el.get("name") or el.get("attributes", {}).get("data-test") or el.get("attributes", {}).get("placeholder")
        if unique_key and unique_key not in seen:
            deduped.append(el)
            seen.add(unique_key)
    return deduped


def generate_hoverable_image_buttons(image_folder, image_list, preview_width=300, preview_height=225):
    html_buttons = ""

    for image_name in image_list:
        image_path = os.path.join(image_folder, image_name).replace("\\", "/")
        with open(image_path, "rb") as img_file:
            encoded_image = base64.b64encode(img_file.read()).decode()

        html_buttons += f"""
        <div class="hover-img-button" style="display:inline-block; margin:20px; text-align:center;">
            <button 
                class="img-btn"
                data-img="data:image/png;base64,{encoded_image}"
                data-name="{image_name}"
                style="margin-bottom:5px; cursor:pointer;"
            >{image_name}</button>
        </div>
        """

    hover_css_and_script = f"""
    <style>
    #img-preview {{
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        display: none;
        z-index: 9999;
        border: 2px solid #ccc;
        background: white;
        padding: 6px;
        box-shadow: 0 0 8px rgba(0,0,0,0.3);
        text-align: center;
    }}
    </style>

    <div id="img-preview">
        <img id="preview-img" src="" width="{preview_width}" height="{preview_height}" />
        <div id="preview-label" style="font-size:14px; margin-top:4px;"></div>
    </div>

    <script>
    document.addEventListener("DOMContentLoaded", function() {{
        const buttons = document.querySelectorAll('.img-btn');
        const preview = document.getElementById('img-preview');
        const previewImg = document.getElementById('preview-img');
        const previewLabel = document.getElementById('preview-label');

        buttons.forEach(btn => {{
            btn.addEventListener('mouseover', () => {{
                previewImg.src = btn.dataset.img;
                previewLabel.innerText = btn.dataset.name;
                preview.style.display = 'block';
            }});
            btn.addEventListener('mouseout', () => {{
                preview.style.display = 'none';
            }});
            btn.addEventListener('click', () => {{
                const imgName = btn.dataset.name;
                const url = new URL(window.location.href);
                url.searchParams.set("selected", imgName);
                window.location.href = url.toString();
            }});
        }});
    }});
    </script>
    """

    return hover_css_and_script + html_buttons

def accuracy_collect(response_text: str) -> float:
    # More flexible regex: find "Overall Accuracy" followed by any non-digits, then a number%
    match = re.search(r"Overall\s*Accuracy[^0-9]*(\d+\.?\d*)\s*%", response_text, re.IGNORECASE)

    if match:
        overall_accuracy = float(match.group(1))
    else:
        # Fallback: try computing from "Score" columns in tables
        scores = re.findall(r"\|\s*\d+\s*\|\s*[^\|]+\|\s*[A-Z/]+\s*\|\s*[^\|]+\|\s*(\d+)", response_text)
        if scores:
            scores = [float(s) for s in scores]
            overall_accuracy = sum(scores) / len(scores)
        else:
            overall_accuracy = 0.0

    return overall_accuracy


import re
import pandas as pd

def parse_ai_testcase_output(ai_response: str):
    """
    Parses AI Markdown table response into structured DataFrames:
    - Technique-level table with emoji scores
    - Scenario summary table
    - Overall accuracy visual
    """
    # Step 1: Flexible regex to capture table rows
    row_pattern = re.compile(
        r'^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(\w+)\s*\|\s*(.*?)\s*\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|',
        re.MULTILINE | re.DOTALL
    )
    matches = row_pattern.findall(ai_response)

    if not matches:
        # fallback: detect tables even if extra spaces/newlines
        row_pattern_fallback = re.compile(r'^\|\s*(\d+)\s*\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|', re.MULTILINE | re.DOTALL)
        matches = row_pattern_fallback.findall(ai_response)
        if not matches:
            raise ValueError("No table rows detected in AI response. Ensure AI output is a Markdown table with pipes '|'.")

    data = []
    for m in matches:
        scenario_id, description, technique, parameters, score, gaps, suggestions = m
        data.append({
            "Scenario ID": int(scenario_id.strip()),
            "Scenario Description": description.strip(),
            "Technique": technique.strip(),
            "Parameters / Factors": parameters.strip(),
            "Score": int(score.strip()),
            "Gaps": gaps.strip(),
            "Suggestions": suggestions.strip()
        })

    df = pd.DataFrame(data)

    # Step 2: Per-scenario summary
    scenario_summary = df.groupby(["Scenario ID", "Scenario Description"]).agg({
        "Score": "mean",
        "Gaps": lambda x: "; ".join([g for g in x if g and g.lower() != "none"]),
        "Suggestions": lambda x: "; ".join([s for s in x if s and s.lower() != "none"])
    }).reset_index()

    scenario_summary.rename(columns={
        "Score": "Overall Coverage (%)",
        "Gaps": "Key Gaps",
        "Suggestions": "Key Suggestions"
    }, inplace=True)

    # Step 3: Add emoji to technique-level scores
    def score_emoji(score):
        if score >= 90:
            return f"✅{score}"
        elif score >= 75:
            return f"⚠️{score}"
        else:
            return f"❌{score}"

    df["Score"] = df["Score"].apply(score_emoji)

    # Step 4: Overall Accuracy
    overall_accuracy = scenario_summary["Overall Coverage (%)"].mean()
    def progress_bar(percentage, length=20):
        filled = int(length * percentage / 100)
        empty = length - filled
        return f"[{'█'*filled}{' ' * empty}] {percentage:.2f}%"

    overall_accuracy_visual = progress_bar(overall_accuracy)

    return df, scenario_summary, overall_accuracy, overall_accuracy_visual

import re
import pandas as pd

def clean_ai_testcase_output(ai_response: str):
    """
    Parse AI response with test case tables into:
    - df_techniques: technique-level table without duplicates
    - df_summary: clean scenario summary
    - overall_accuracy: float
    - overall_visual: progress bar string
    """
    # 1. Split by scenarios
    scenario_blocks = re.split(r'#+\s*Scenario \d+:', ai_response, flags=re.IGNORECASE)

    tech_rows = []
    summary_rows = []

    for block in scenario_blocks[1:]:
        # Scenario ID and Description
        header_match = re.match(r'\s*(\d+)?[:\s-]*(.+)', block)
        scenario_id = header_match.group(1) if header_match else "Unknown"
        description = header_match.group(2).split('\n')[0].strip() if header_match else "Unknown"

        # Extract table rows (avoid header separators)
        table_lines = [line for line in block.split('\n') if re.match(r'^\|', line)]
        for line in table_lines:
            cols = [c.strip() for c in line.strip('|').split('|')]
            if len(cols) >= 7:  # Technique-level
                technique, params, score, gaps, suggestions = cols[2], cols[3], cols[4], cols[5], cols[6]
                # Clean score to int
                try:
                    score_num = int(re.sub(r'\D', '', score))
                except:
                    score_num = 0
                # Emoji indicator
                if score_num >= 90: score_display = f"✅{score_num}"
                elif score_num >= 75: score_display = f"⚠️{score_num}"
                else: score_display = f"❌{score_num}"

                tech_rows.append({
                    "Scenario ID": scenario_id,
                    "Scenario Description": description,
                    "Technique": technique,
                    "Parameters / Factors": params,
                    "Score": score_display,
                    "Gaps": gaps if gaps != "None" else "",
                    "Suggestions": suggestions if suggestions != "None" else ""
                })

        # Compute Overall Coverage per scenario (average of technique scores)
        scores = []
        for line in table_lines:
            cols = [c.strip() for c in line.strip('|').split('|')]
            if len(cols) >= 7:
                try:
                    scores.append(int(re.sub(r'\D', '', cols[4])))
                except: pass
        overall = round(sum(scores)/len(scores),2) if scores else 0

        # Merge Gaps and Suggestions
        gaps = ', '.join([r['Gaps'] for r in tech_rows if r['Scenario ID'] == scenario_id and r['Gaps']])
        suggestions = ', '.join([r['Suggestions'] for r in tech_rows if r['Scenario ID'] == scenario_id and r['Suggestions']])

        summary_rows.append({
            "Scenario ID": scenario_id,
            "Scenario Description": description,
            "Overall Coverage (%)": overall,
            "Key Gaps": gaps,
            "Key Suggestions": suggestions
        })

    df_techniques = pd.DataFrame(tech_rows).drop_duplicates()
    df_summary = pd.DataFrame(summary_rows)

    # Overall Accuracy
    overall_accuracy = df_summary["Overall Coverage (%)"].mean() if not df_summary.empty else 0
    bar_len = 20
    filled = int(bar_len * overall_accuracy / 100)
    overall_visual = f"[{'█'*filled}{' '*(bar_len-filled)}] {overall_accuracy:.2f}%"

    return df_techniques, df_summary, overall_accuracy, overall_visual
#### max test cases

def testcase_requirement_split(prompt_type,image_data,action_data=None):
    prompt_template = load_prompt_from_file(prompt_type)
    # Conditionally inject Action Data section or leave it blank
    if action_data:
        action_section = f"- User Interaction Elements (Action Data): {action_data}"
    else:
        action_section = ""
    final_prompt = prompt_template.format(ACTION_DATA=action_data,IMAGE_DATA=image_data)
    print(final_prompt)
    # Set environment variables (if needed)
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    os.environ["AZURE_OPENAI_API_KEY"] = api_key
    os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint

    # Initialize the model
    model = AzureChatOpenAI(
        openai_api_version="2023-05-15",
        azure_deployment="qepracticekey",
    )
    message = HumanMessage(content=final_prompt)
    response = model([message])
    # Extract text from response
    if hasattr(response, "content"):
        response_text = response.content
    elif isinstance(response, dict) and "content" in response:
        response_text = response["content"]
    else:
        response_text = str(response)

    # Parse as JSON
    try:
        result_json = json.loads(response_text)
    except json.JSONDecodeError:
        raise ValueError("Model did not return valid JSON. Raw output:\n" + response_text)

    return result_json


def get_full_testcases(formatted_summary):
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

    os.environ["AZURE_OPENAI_API_KEY"] = api_key
    os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint

    model = AzureChatOpenAI(
        openai_api_version="2023-05-15",
        azure_deployment="qepracticekey",
        max_tokens=4000,   # allow long responses
        temperature=0
    )

    collected_output = ""
    while True:
        # Always provide original instructions + progress so far
        messages = [
            HumanMessage(content=formatted_summary),
            HumanMessage(content="Progress so far:\n" + collected_output),
            HumanMessage(content="Continue generating test cases from the last step. "
                                 "Do not repeat previous cases. Do not summarize. "
                                 "Keep the same Markdown table format.")
        ]

        response = model(messages)
        response_text = response.content.strip()
        collected_output += "\n" + response_text

        # ✅ Stop once we see 20 complete test cases
        if collected_output.count("| Test Case") >= 20:
            break

        # ✅ Safety check: stop if model keeps looping
        if "Continued in next response" not in response_text and len(response_text) < 50:
            break

    return collected_output