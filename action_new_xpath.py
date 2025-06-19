from github import Github
import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait
import os
import threading
import time
import Utilities_Xpath as utils
import utils_action as action_utils
from PIL import Image
from Utilities import *
import pytesseract
from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
# Setup output folder
current_path = os.getcwd()
input_folder = os.path.join(current_path, "Input")
output_folder = os.path.join(current_path, "output")
Action_collection = os.path.join(output_folder, "Action_collection")
Page_collection = os.path.join(output_folder, "page_file_generator")
Test_case_collection = os.path.join(output_folder, "Test_Cases_collection")
Test_file_generator = os.path.join(output_folder, "test_file_generator")
feature_file_collection = os.path.join(output_folder, "Feature_file_generator")
os.makedirs(Page_collection, exist_ok=True)
os.makedirs(Test_case_collection, exist_ok=True)
os.makedirs(Action_collection, exist_ok=True)
os.makedirs(feature_file_collection, exist_ok=True)
page_screenshot_folder = os.path.join(Action_collection, "page_screenshot")
os.makedirs(page_screenshot_folder, exist_ok=True)
os.makedirs(Test_file_generator, exist_ok=True)

st.set_page_config(
    page_title="TigerQE One Stop AI Solution",
    page_icon="🤖",
    layout="centered"
)

# Session state setup
if "page_url" not in st.session_state:
    st.session_state.page_url=None
if "repo_url" not in st.session_state:
    st.session_state.repo_url=None
if "selected_images" not in st.session_state:
    st.session_state.selected_images = []
if "show_popup" not in st.session_state:
    st.session_state.show_popup = False
if "show_form" not in st.session_state:
    st.session_state.show_form = False
if 'stop_monitor' not in st.session_state:
    st.session_state.stop_monitor = {"stop": False}
if 'monitor_thread' not in st.session_state:
    st.session_state.monitor_thread = None
if 'driver' not in st.session_state:
    st.session_state.driver = None
if 'recording_started' not in st.session_state:
    st.session_state.recording_started = False
if 'actions' not in st.session_state:
    st.session_state.actions = []
if 'selected_xpaths' not in st.session_state:
    st.session_state.selected_xpaths = []
if 'prompt_response' not in st.session_state:
    st.session_state.prompt_response = ""
if 'prompt_response_page_file' not in st.session_state:
    st.session_state.prompt_response_page_file=""
if 'last_page' not in st.session_state:
    st.session_state.last_page = None
if 'selected_tags' not in st.session_state:
        st.session_state.selected_tags = []
if 'selected_app' not in st.session_state:
    st.session_state.selected_app = []
# Unique key for session state
if "scroll_to_top" not in st.session_state:
    st.session_state.scroll_to_top = False
if "checkbox1_state" not in st.session_state:
    st.session_state.checkbox1_state = True
if "checkbox2_state" not in st.session_state:
    st.session_state.checkbox2_state = False
if "checkbox3_state" not in st.session_state:
    st.session_state.checkbox3_state = True
if "checkbox4_state" not in st.session_state:
    st.session_state.checkbox4_state = True
if "checkbox5_state" not in st.session_state:
    st.session_state.checkbox5_state = True
if "checkbox6_state" not in st.session_state:
    st.session_state.checkbox6_state = True

st.title(" 🤖 TigerQE 'One-Stop' AI Solution")
# 1. Open the browser
page_url = st.text_input("Enter the URL of the page:")
st.session_state.page_url = page_url
if st.button("Open Browser"):
    if page_url:
        chrome_options = Options()
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        st.session_state.driver = webdriver.Chrome(options=chrome_options)
        st.session_state.driver.get(page_url)
        st.session_state.driver.maximize_window()
        WebDriverWait(st.session_state.driver, 30).until(utils.is_page_loaded)
        st.success("✅ Browser opened and ready.")

# Display sections based on checkboxes
if st.session_state.checkbox1_state:
    with st.expander("🔴 User Workflow Recorder"):
        # 2. Start Recording
        st.subheader("Record User Actions & Capture Screenshots of User Navigation")
        if not st.session_state.recording_started and st.button("🎥 Start Recording"):
            if st.session_state.driver:
                st.session_state.actions = [] # reset if previously recorded
                action_utils.start_recording(st.session_state.driver)
                st.session_state.recording_started = True

                # Start thread to monitor URL and take screenshots
                st.session_state.stop_monitor = {"stop": False}
                st.session_state.monitor_thread = threading.Thread(
                    target=utils.monitor_url_changes,
                    args=(st.session_state.driver, page_screenshot_folder, st.session_state.stop_monitor),
                    daemon=True
                )
                st.session_state.monitor_thread.start()
                st.success("Recording started. Please interact in the browser.")

        # 3. Stop Recording
        if st.session_state.recording_started and st.button("🛑 Stop Recording"):
            st.session_state.actions = action_utils.get_recorded_actions(st.session_state.driver)
            st.session_state.recording_started = False
            #st.session_state.actions = actions
            # Stop the monitoring thread
            st.session_state.stop_monitor["stop"] = True
            if st.session_state.monitor_thread:
                st.session_state.monitor_thread.join()
            st.success(f"Recording stopped. {len(st.session_state.actions)} actions captured.")
            actions=[]

        # 4. Show and Save Actions
        if st.session_state.actions:

            page_name = st.text_input("Enter Page Name for Saving the Workflow:")
            if st.button("💾 Save Workflow"):
                workflow_text = action_utils.generate_workflow(st.session_state.actions)
                if page_name:
                    filename = os.path.join(Action_collection, f"{page_name}_actions.txt")
                    with open(filename, "w") as f:
                        f.write("\n".join(workflow_text))  # ✅ FIXED
                    st.success(f"✅ Workflow saved: {filename}")
                    st.download_button("⬇ Download Workflow", data="\n".join(workflow_text),
                                    file_name=f"{page_name}_actions.txt")
                    st.session_state.actions = []  # clear after save
                    st.session_state.show_popup = True
                    st.session_state.show_form = False  # Reset form visibility
                else:
                    st.warning("⚠ Please enter a name for the workflow.")

if st.session_state.checkbox2_state:
    with st.expander("🧾 BDD Feature File Generator"):
        st.title("Feature file Generator using recorded actions")
        Feature_file_name = st.text_input("Enter feature file Name")
        Action_data = utils.select_and_read_text_files_xpath("feature",Action_collection)
        action_prompt = f"""Summarize the following context into a concise and structured format (under 100 lines), preserving key actions, entities, and sequences. The goal is to retain essential meaning for AI understanding, automation, or test case generation. Avoid repetition, and group related items logically. Context: {Action_data} """
        action_data_processed = utils.get_queries_from_ai_updated(action_prompt)
        feature_prompt = utils.generate_pom_from_excel_feature("featurefile", action_data_processed)
        if st.button("Generate_feature_File"):
            feature_response=utils.get_queries_from_ai_updated(feature_prompt)
            save_feature_file = os.path.join(feature_file_collection, f"{Feature_file_name}.feature")
            with open(save_feature_file, "w") as file:
                file.write(feature_response.strip())

            st.write(f"Feature file saved here: {save_feature_file}")

if st.session_state.checkbox3_state:
    with st.expander("🧮 E2E Test Case Generator"):

        st.title("E2E Test Case Generation")

        option = st.radio(
            "Choose your Flow with:",
            ('Documents', 'Recorded_details')
        )

        if option == 'Recorded_details':
            # Show image selection and prompt box
            st.markdown("**Select Images (Mandatory)** <span style='color:red;'>*</span>", unsafe_allow_html=True)
            image_files = [f for f in os.listdir(page_screenshot_folder) if
                           f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
            cols = st.columns(5)
            for idx, image_file in enumerate(image_files):
                with cols[idx % 5]:
                    st.image(os.path.join(page_screenshot_folder, image_file), width=100)
                    if image_file not in st.session_state.selected_images:
                        if st.button(f"{image_file}", key=f"{image_file}"):
                            st.session_state.selected_images.append(image_file)
                    else:
                        if st.button(f"Deselect {image_file}", key=f"deselect_{image_file}"):
                            st.session_state.selected_images.remove(image_file)

            if st.session_state.selected_images:
                st.write("### Selected images in order:")
                for i, img_name in enumerate(st.session_state.selected_images, 1):
                    st.write(f"{i}. {img_name}")

            if st.button("Clear All Selection"):
                st.session_state.selected_images = []
            st.markdown("**Enter the prompt Functional Test Case** <span style='color:red;'>*</span>",
                        unsafe_allow_html=True)
            prompt = st.text_area('', '')
            st.markdown("**Please select relevent action file(Optional)**", unsafe_allow_html=True)
            Action_data = utils.select_and_read_text_files(Action_collection)

        elif option == 'Documents':
            # Show only document upload section
            # st.write("Upload a PDF, Word, or Excel document:")
            st.markdown("**Upload a PDF, Word, or Excel document** <span style='color:red;'>*</span>",
                        unsafe_allow_html=True)
            uploaded_file = st.file_uploader("", type=['pdf', 'docx', 'xlsx'])

            if uploaded_file is not None:
                if utils.allowed_file(uploaded_file.name, ['pdf']):
                    st.success("PDF file uploaded successfully!")
                elif utils.allowed_file(uploaded_file.name, ['docx']):
                    st.success("Word file uploaded successfully!")
                elif utils.allowed_file(uploaded_file.name, ['xlsx']):
                    st.success("Excel file uploaded successfully!")
                else:
                    st.error("Unsupported file format.")
        if st.button("Generate Functional Test Cases"):
            # st.write(Action_data)
            if option == 'Recorded_details':
                if st.session_state.selected_images and prompt:
                    # Construct navigation as a comma-separated string
                    navigation = ', '.join(st.session_state.selected_images)
                    # st.write(navigation)

                    # Finding images in the pages folder and extracting text using pytesseract
                    image_data = ""
                    for image_name in st.session_state.selected_images:
                        image_path = os.path.join(page_screenshot_folder, image_name)
                        if os.path.exists(image_path):
                            # Display the uploaded image
                            image = Image.open(image_path)
                            st.image(image, caption=image_name, use_container_width=True)

                            # Extract text from the image using pytesseract
                            try:
                                extracted_text = pytesseract.image_to_string(image)
                                if extracted_text:
                                    image_data += f"\nImage: {image_name}\nExtracted Text: {extracted_text}\n"
                                else:
                                    image_data += f"\nImage: {image_name}\nExtracted Text: No text found\n"
                            except Exception as e:
                                st.error(f"Error extracting text from {image_name}: {e}")
                        else:
                            st.error(f"Image not found: {image_name}")
                    image_prompt = f"""Summarize the following context into a concise and structured format (under 100 lines), preserving key actions, entities, and sequences. The goal is to retain essential meaning for AI understanding, automation, or test case generation. Avoid repetition, and group related items logically. Context: {image_data} """
                    print(image_prompt)
                    image_data_processed = utils.get_queries_from_ai_updated(image_prompt)
                    print(image_data_processed)
                    action_prompt = f"""Summarize the following context into a concise and structured format (under 100 lines), preserving key actions, entities, and sequences. The goal is to retain essential meaning for AI understanding, automation, or test case generation. Avoid repetition, and group related items logically. Context: {Action_data} """
                    action_data_processed = utils.get_queries_from_ai_updated(action_prompt)
                    print(action_data_processed)
                    if not action_data_processed:
                        action_data_processed = None
                    constructedprompt = utils.generate_pom_from_excel_testcases("Test_case_generation", navigation,
                                                                                image_data_processed, action_data_processed,
                                                                                prompt)
                    prompt_response = utils.get_queries_from_ai_updated(constructedprompt)
                    st.code(prompt_response)
                    utils.covert_response_to_testcases(prompt_response, Test_case_collection)
            elif option == 'Documents' and uploaded_file is not None:
                    extracted_data = utils.extract_text_from_pdf(uploaded_file)
                    constructedprompt = utils.generate_excel_testcases_with_document("Test_case_generation_document",
                                                                                     extracted_data)
                    prompt_response = utils.get_queries_from_ai_updated(constructedprompt)
                    st.code(prompt_response)
                    utils.covert_response_to_testcases(prompt_response, Test_case_collection)
if st.session_state.checkbox4_state:
    with st.expander("🔎 Xpath 🧾 Page File Generator"):
        st.title("XPath Generator for Visible Elements")
        # page_url = st.text_input("Enter the URL of the page:")
        selected_app = st.multiselect(
            "Select application type:",
            ["PowerBi", "Web"],
            default=["Web"])
        tags_placeholder = st.empty()
        if "Web" in selected_app:
            selected_tags = tags_placeholder.multiselect(
                "Select element types to extract:",
                ["input", "button", "a", "select", "textarea", "div", "span", "All"],
                default=["input", "button"]
            )
        else:
            tags_placeholder.empty()  # Hides the tag selection for PowerBi only
            selected_tags = []  # No tags for PowerBi
        st.session_state.selected_tags = selected_tags
        st.session_state.selected_app = selected_app
        st.markdown("<a name='top-button'></a>", unsafe_allow_html=True)
        collect_clicked = st.button("Collecting Elements", key="collect_btn")
        if collect_clicked:
            formatted_summary = None
            st.session_state.selected_xpaths = []
            st.session_state.prompt_response = ""
            page_identifier = st.session_state.driver.current_url  # Collect visible elements
            if "PowerBi" in selected_app:
                formatted_summary = utils.get_visible_element_powerBi(st.session_state.driver, page_identifier)
                # get_visible_element_iframe(st.session_state.driver,page_identifier,st.session_state.selected_tags))
            if "Web" in selected_app:
                formatted_summary = utils.get_visible_element_iframe(st.session_state.driver, page_identifier,
                                                                    st.session_state.selected_tags)
            if formatted_summary is None:
                formatted_summary = []
            if formatted_summary:
                if "PowerBi" in selected_app:
                    # prompt = f"Generate multiple XPath expressions for the input and button elements based on the following details. Consider various attributes, hierarchy levels, and text content to create comprehensive XPath variations for each element: {formatted_summary}"
                    st.session_state.prompt_response = utils.get_queries_from_ai("PowerBi", formatted_summary)
                    print("OPen Ai response" + st.session_state.prompt_response)
                if "Web" in selected_app:
                    # prompt = f"Generate multiple XPath expressions for the input and button elements based on the following details. Consider various attributes, hierarchy levels, and text content to create comprehensive XPath variations for each element: {formatted_summary}"
                    st.session_state.prompt_response = utils.get_queries_from_ai("Web", formatted_summary)
                    print("OPen Ai response" + st.session_state.prompt_response)
            else:
                st.info("No elements found in selected tag")
            # Simulate the AI response for demonstration

        # Display the XPath selection UI only after receiving a prompt response
        if st.session_state.prompt_response:
            xpath_dict = utils.filter_duplicate_xpaths(utils.selecting_xpath(st.session_state.prompt_response))
            print(xpath_dict)
            st.title("Select XPath Expressions to Add to Excel")

            st.session_state.selected_xpaths = utils.adding_xapth_user_view(xpath_dict)
            page_name = st.text_input("Enter the Page Name:")
            # Show "Add Selected XPaths to Excel" button only after XPaths are displayed
            if st.button("Add Selected XPaths to Excel"):
                print("going inside add excel")
                print(st.session_state.selected_xpaths)
                if st.session_state.selected_xpaths:
                    print("going inside add excel")
                    utils.adding_selected_xapth_excel(page_name)
                    st.session_state.show_popup = True
                    st.session_state.show_form = False  # Reset form visibility
                # Show popup only if the flag is set
        if st.session_state.show_popup and not st.session_state.show_form:
            st.write("**Do you want to generate the page file?**")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Yes"):
                    st.session_state.show_popup = False  # Hide popup
                    st.session_state.show_form = True  # Show form for page file generation

            with col2:
                if st.button("No"):
                    st.session_state.show_popup = False
                    st.session_state.show_form = False
                    st.write("Page file generation skipped.")
        # Show popup only if the flag is set
        if st.session_state.show_form:
            st.write("Generating Page File")
            page_name = st.text_input("Enter Page Name", value=page_name)
            language = st.selectbox("Select Language", ["java", "python", "c#", "javascript"])
            Action_data = utils.select_and_read_text_files_xpath("xpath",Action_collection)
            action_prompt = f"""Summarize the following context into a concise and structured format (under 100 lines), preserving key actions, entities, and sequences. The goal is to retain essential meaning for AI understanding, automation, or test case generation. Avoid repetition, and group related items logically. Context: {Action_data} """
            action_data_processed = utils.get_queries_from_ai_updated(action_prompt)

            if st.button("Generate Page File"):
                st.session_state.prompt_response_page_file = ""
                Prompt = utils.generate_pom_from_excel_with_action("Page_File_Action", page_name, language, action_data_processed)
                st.session_state.prompt_response_page_file = utils.get_queries_from_ai("Page_File", Prompt)
                st.subheader("Generated Page Class")
                utils.create_java_file(page_name, language, st.session_state.prompt_response_page_file)
                # with open("GeneratedTest.java", "w") as file:
                #     file.write(st.session_state.prompt_response)
                # print("✅ Java test script generated: GeneratedTest.java")
                # st.code(st.session_state.prompt_response)
                # Placeholder for your page file generation script
                st.success(f"Page file generated for '{page_name}' in '{language}' language.")
                # Trigger scroll with 'Continue' button
                # if st.button("Continue"):
                #     utils.scroll_and_focus()

        # Handle the "Find XPath" button logic
        if st.session_state.driver:
            if st.button("Find XPath for new page"):
                formatted_summary = None
                st.session_state.selected_xpaths = []
                st.session_state.prompt_response = ""
                st.session_state.prompt_response_page_file = ""
                st.session_state.show_popup = False
                st.session_state.show_form = False
                utils.loading_newpage(st.session_state.driver)
                page_identifier = st.session_state.driver.current_url

                if "PowerBi" in selected_app:
                    formatted_summary = utils.get_visible_element_powerBi(st.session_state.driver, page_identifier)
                if "Web" in selected_app:
                    formatted_summary = utils.get_visible_element_iframe(st.session_state.driver, page_identifier,
                                                                        selected_tags)
                # Ensure current_elements is always defined (even if empty)
                if formatted_summary is None:
                    formatted_summary = []
                if formatted_summary:
                    if "PowerBi" in selected_app:
                        # prompt = f"Generate multiple XPath expressions for the input and button elements based on the following details. Consider various attributes, hierarchy levels, and text content to create comprehensive XPath variations for each element: {formatted_summary}"
                        st.session_state.prompt_response = utils.get_queries_from_ai("PowerBi", formatted_summary)
                        print("OPen Ai response" + st.session_state.prompt_response)
                    if "Web" in selected_app:
                        # prompt = f"Generate multiple XPath expressions for the input and button elements based on the following details. Consider various attributes, hierarchy levels, and text content to create comprehensive XPath variations for each element: {formatted_summary}"
                        st.session_state.prompt_response = utils.get_queries_from_ai("Web", formatted_summary)
                        print("OPen Ai response" + st.session_state.prompt_response)
                    # prompt = f"Generate multiple XPath expressions for the input and button elements based on the following details. Consider various attributes, hierarchy levels, and text content to create comprehensive XPath variations for each element: {current_elements}"
                    # st.session_state.prompt_response = get_queries_from_ai(prompt)
                    # print("open Ai Reponse" + st.session_state.prompt_response)
                else:
                    st.info("No elements found in selected tag")

                # Display the XPath selection UI only after receiving a prompt response
                if st.session_state.prompt_response:
                    xpath_dict = utils.filter_duplicate_xpaths(utils.selecting_xpath(st.session_state.prompt_response))
                    print(xpath_dict)

                    st.title("Select XPath Expressions from new page to Add to Excel")
                    try:
                        utils.adding_xapth_user_view(xpath_dict)
                    except (Exception) as e:
                        print(e)
                    new_page_name = st.text_input("Enter the New Page Name:", key="new_page_name")
                    # new_page_name = st.text_input("Enter the New Page Name:")
                    # Show "Add Selected XPaths to Excel" button only after XPaths are displayed
                    Add_to_excel = st.button("Add Selected XPaths to Excel", key="add_to_excel_new")
                    if Add_to_excel:
                        if st.session_state.selected_xpaths:
                            utils.adding_selected_xapth_excel(new_page_name)
                            st.session_state.show_popup = True
                            st.session_state.show_form = False  # Reset form visibility
                        # Show popup only if the flag is set
                        if st.session_state.show_popup and not st.session_state.show_form:
                            st.write("**Do you want to generate the page file?**")

                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("Yes"):
                                    st.session_state.show_popup = False  # Hide popup
                                    st.session_state.show_form = True  # Show form for page file generation

                            with col2:
                                if st.button("No"):
                                    st.session_state.show_popup = False
                                    st.session_state.show_form = False
                                    st.write("Page file generation skipped.")
                        # Show popup only if the flag is set
                        if st.session_state.show_form:
                            st.write("Generating Page File")
                            page_name = st.text_input("Enter Page Name", value=page_name)
                            language = st.selectbox("Select Language", ["java", "python", "c#", "javascript"])
                            Action_data = utils.select_and_read_text_files_xpath("xpath", Action_collection)
                            if st.button("Generate Page File"):
                                st.session_state.prompt_response_page_file = ""
                                Prompt = utils.generate_pom_from_excel_with_action("Page_File_Action", page_name, language,Action_data)
                                st.session_state.prompt_response_page_file = utils.get_queries_from_ai("Page_File", Prompt)
                                st.subheader("Generated Page Class")
                                utils.create_java_file(page_name, language, st.session_state.prompt_response_page_file)
                                st.session_state.show_popup = False
                                st.session_state.show_form = False
                                st.success(f"Page file generated for '{page_name}' in '{language}' language.")
                                # Trigger scroll with 'Continue' button
                                # if st.button("Continue"):
                                #     utils.scroll_and_focus()

    if st.session_state.checkbox5_state:
        with st.expander("🧾 Test Automation Script Generator"):
            st.title("Automation Script Generator using page file and test cases")
            test_file_name=st.text_input("Enter the test File Name")
            test_file_language = st.selectbox("Select Language for test file", ["java", "python", "c#", "javascript"])
            page_files_content = utils.select_and_read_text_files_xpath("page_test", Page_collection)
            test_files_content = utils.select_and_read_text_files_xpath("testcase_test",Test_case_collection)
            if st.button("Generate_Test_Script"):
                Prompt = utils.generate_test_script("Test_File_Action", test_file_language, page_files_content,test_files_content)
                test_script_response= utils.get_queries_from_ai_updated(Prompt)
                #st.write(test_script_response)
                utils.create_test_file(Test_file_generator,test_file_name, test_file_language, test_script_response)

if st.session_state.checkbox6_state:
    from github import Github, GithubException  # Make sure GithubException is imported

    with st.expander("⚙️ GitHub 📡 Automation Bridge"):
        st.title("Upload code to Repository")

        pytest_files = utils.select_and_read_text_files_xpath("pom_file", utils.Test_file_generator)
        repo_pytest_name = st.text_input("Enter folder name in repo:", value="test_web/tests/test_cases")

        pom_files = utils.select_and_read_text_files_xpath("test_file", utils.Page_file_generator)
        repo_pom_name = st.text_input("Enter folder name in repo:", value="test_web/src/pom/pages")

        if st.button("Push to Repo"):

            g = Github(os.getenv("GITHUB_ACCESS_TOKEN"))
            repo = g.get_repo(os.getenv("GITHUB_REPO_NAME"))
            branch = os.getenv("GITHUB_BRANCH_NAME", "main")

            if repo_pom_name and repo_pytest_name:

                # Push all POM files
                for file_name, content in pom_files.items():
                    pom_dest_path = f"{repo_pom_name.strip('/')}/{file_name}"
                    utils.push_file_to_github(pom_dest_path, content, repo, branch)

                # Push all pytest files
                for file_name, content in pytest_files.items():
                    pytest_dest_path = f"{repo_pytest_name.strip('/')}/{file_name}"
                    utils.push_file_to_github(pytest_dest_path, content, repo, branch)

            else:
                st.warning("⚠️ Please enter both folder names in the repo.")

st.markdown("""    
    ### Contact Us
    - Reach us at [QE Core Team](mailto:QE@tigeranalytics.com)


    ### Want to learn more?
    - Check out [streamlit.io](https://streamlit.io)

""")

# Create 6 columns
col0, col1, col2, col3, col4, col5, col6 = st.columns(7)

with col0:
    st.write("Choose display")
with col1:
    checkbox1 = st.checkbox("(1)", value=st.session_state.checkbox1_state)
    if st.session_state.checkbox1_state != checkbox1:
        st.session_state.checkbox1_state = checkbox1  # Update session state
        st.rerun()
with col2:
    checkbox2 = st.checkbox("(2)", value=st.session_state.checkbox2_state)
    if st.session_state.checkbox2_state != checkbox2:
        st.session_state.checkbox2_state = checkbox2  # Update session state
        st.rerun()
with col3:
    checkbox3 = st.checkbox("(3)", value=st.session_state.checkbox3_state)
    if st.session_state.checkbox3_state != checkbox3:
        st.session_state.checkbox3_state = checkbox3  # Update session state
        st.rerun()
with col4:
    checkbox4 = st.checkbox("(4)", value=st.session_state.checkbox4_state)
    if st.session_state.checkbox4_state != checkbox4:
        st.session_state.checkbox4_state = checkbox4  # Update session state
        st.rerun()
with col5:
    checkbox5 = st.checkbox("(5)", value=st.session_state.checkbox5_state)
    if st.session_state.checkbox5_state != checkbox5:
        st.session_state.checkbox5_state = checkbox5  # Update session state
        st.rerun()
with col6:
    checkbox6 = st.checkbox("(6)", value=st.session_state.checkbox6_state)
    if st.session_state.checkbox6_state != checkbox6:
        st.session_state.checkbox6_state = checkbox6  # Update session state
        st.rerun()
