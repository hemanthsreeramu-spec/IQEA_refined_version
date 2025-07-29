prompt_list = [
    {
        "prompt_name": "featurefile_prompt",
        "prompt_text": """You are a Behaviour Driven Development (BDD) assistant.
Generate a .feature file using Gherkin syntax based on the recorded user actions provided below.
Output only valid .feature file content—do not include explanations, notes, or any extra text.

Each scenario should:
Represent a page or logical workflow step.
Use appropriate Given, When, Then, And steps.
Accurately reflect the actions users performed.
Use readable and testable language for automation.
Do not include any explanations, summaries, or additional comments—only the feature file content.

Recorded User Actions: 
{recorded_action}""",
        "description": "Prompt to generate BDD feature files based on user requirements"
    },
    {
        "prompt_name": "powerbi_prompt",
        "prompt_text": """You are a skilled XPath expert.

Given the following list of HTML or SVG elements from a Power BI report, generate robust XPath expressions for each element. Follow these guidelines:
Generate XPath expressions for each of the following HTML elements, ensuring to cover all relevant attributes like tag, class, id, and text. Provide XPath expressions for elements based on these attributes. Handle cases where there are multiple elements with the same class or text by incorporating appropriate unique identifiers. The attributes in the input may vary for different tags and should be handled accordingly.
### General Rules:
- For each element in the input list:
  - Ensure every element has a generated XPath, even if the text is empty.
  - For each element, provide a clear, readable description and a robust XPath expression
- For elements with text:
  - If text is nested, always use:
    `//*[contains(@class, '...')]//*[contains(text(), '...')]`.
  - Avoid `and` conditions for text matching.
  - Ensure text matches are flexible with `contains()`.

- For elements with class names but without text:
  - Use `//*[contains(@class, '...')]` to match elements.
  - For any nested elements, use `//*` to capture all.

- The XPath should be as specific and flexible as possible, accommodating both HTML and SVG contexts.

### Special Rules for Graph Elements:
- For labels within graphs:
  `//*[contains(@class,'cartesianChart')]//*[@class='label-container']//*[contains(text(), '...')]`

- For axis ticks in graphs:
  `//*[contains(@class,'cartesianChart')]//child::*[@class='tick']//*[contains(text(), '...')]`

- For graph titles:
  `//*[contains(@class,'cartesianChart')]//following::*[contains(@class,'visualTitle')]//*[contains(text(), '...')]`

### Additional Handling:
- If an element is a `visual-container` with text, always use:
  `//*[contains(@class,'visual-container')]//*[contains(text(), '...')]`
- For SVG text, use:
  `//*[name()='svg']//*[contains(text(), '...')]`.

### Input Elements:
{formatted_summary}

### Expected Output Format:
[
  {{
    "description": "Readable description of the element",
    "xpath": "Generated XPath (flexible and correct)"
  }},
  ...
]""",
        "description": "Prompt for Power BI dashboards - extract from visuals"
    },
    {
        "prompt_name": "web_prompt",
        "prompt_text": """From the given list of elements, generate all possible XPath expressions for each element using its tag and attributes only.
Return only valid XPath strings as output. Do not include any explanation or description.

Input: {formatted_summary}""",
        "description": "Prompt for generic web iframe/table scraping"
    },
    {
        "prompt_name": "pagefile_prompt",
        "prompt_text": """Generate a complete {language} Page Object Model (POM) class file using Selenium, with the following elements:
{xpaths}

Requirements:
1. Use @FindBy annotation with How.XPATH for element identification.
2. Initialize WebDriver and use PageFactory.initElements() in the constructor.
3. Provide methods for each element (e.g., enterText(), clickButton()).
4. Use meaningful naming conventions for class, methods, and variables.
5. Only generate the complete Java file content without any additional explanation or comments.
6. Ensure the class name is based on the page name, and it must be a valid Java class name.
7. Do not include any unnecessary comments or extra text.""",
        "description": "Prompt to dynamically generate page file"
    },
    {
        "prompt_name": "pagefile_action_prompt",
        "prompt_text": """Generate a complete {language} Page Object Model (POM) class using Selenium.

Inputs:
1. Elements (with XPaths):
{xpaths}

2. Recorded User Actions (to derive methods and behavior):
{Action_data}

Requirements:
1. Use @FindBy annotation with How.XPATH to locate elements.
2. Initialize WebDriver in the constructor and call PageFactory.initElements().
3. Generate methods based on the recorded actions, using appropriate interaction logic (e.g., sendKeys, click).
4. Method names should reflect the intent of the action (e.g., enterUsername(), clickLoginButton()).
5. Use meaningful and consistent naming conventions for the class, methods, and variables.
6. The class name must be derived from the page name and be a valid {language} class name.
7. Return only the complete and syntactically correct {language} class code — no explanations, comments, or extra output.""",
        "description": "Prompt to dynamically generate page file with recorded actions"
    },
    {
        "prompt_name": "testscript_prompt",
        "prompt_text": """You are a test automation expert.

Your task is to generate a {test_file_language} test script using pytest (or unittest) based on the following inputs. The script should automate all test case steps by utilizing methods from the page object file(s) and ensuring complete execution of the test flow.

## Input 1: Page Object File(s)
{page_files_content}

## Input 2: Test Case Definitions
{test_files_content}

## Instructions:
1. Each test case must be fully implemented, step by step, from start to end—no step should be skipped.
2. For each step:
   - First, check if a matching page method exists and use it.
   - If not, use a matching XPath from the page object.
   - If still not found, write a direct Selenium command.
3. Include assert statements to verify expected outcomes.
4. Follow the test case step order exactly.
5. Create reusable methods for shared flows like login.
6. Use pytest structure as needed.
7. Add clear inline comments for each step.
8. Intelligently infer behavior when needed.
9. Ensure the script is complete, syntactically valid, and executable.

## Output Format:
- Return only valid Python test code.
- Include imports, test class, one function per test case, using page methods/XPath/raw Selenium.""",
        "description": "Prompt to generate the test script"
    },
    {
        "prompt_name": "testcasegenerate_prompt",
        "prompt_text": """You are an expert QA Test Case Generator.

Your task is to generate a comprehensive, logically ordered, end-to-end set of functional test cases using the following inputs:

Inputs:
- Navigation Flow: {navigation}
- UI Layout from Screen Images: {image_data_processed}
{action_data_processed}

Requirements:
{requirements}

Instructions:
1. Start each case from login or the first screen and end at a success/confirmation screen.
2. At least one full end-to-end case is required.
3. Use recorded actions if available, otherwise infer from inputs.
4. Include forms, navigation, validations, edge cases, etc.
5. Use pairwise test coverage.
6. Cover frontend and backend outcomes.

Output Format:
- Markdown tables using:
  Test Case Name | Step Number | Test Step Description | Test Step Expected Result | Status | Type
- Status = "New", Type = "Manual"
- 15–20 test cases, each with 2–6 steps
- No explanations, just raw tables.""",
        "description": "Prompt for generate test cases"
    },
    {
        "prompt_name": "testcasegeneratewithdoc_prompt",
        "prompt_text": """You are an expert QA Test Case Generator.

Your task is to generate a comprehensive set of realistic, end-to-end functional test cases based solely on the extracted requirement text from a document.

Input:
- Extracted Requirement to Validate: {requirements}

Instructions:
1. Follow realistic user flow.
2. Test all fields, buttons, dropdowns, and outputs.
3. Include positive, negative, boundary, edge, retry tests.
4. Use pairwise input combination techniques.

Output Format:
- Markdown table with columns:
  Test Case Name | Step Number | Test Step Description | Test Step Expected Result | Status | Type
- Status = "New"
- Type = "Manual"
- 15–20 test cases, each 2–6 steps
- No extra output or explanation.""",
        "description": "Prompt to generate test cases with uploaded documents"
    },
    {
        "prompt_name": "testcageneartev2_prompt",
        "prompt_text": """You are an expert QA Test Case Generator.

Your task is to generate a comprehensive set of realistic, end-to-end functional test cases to validate a target page or feature using the following inputs:

Inputs:
- Navigation Flow: {navigation}
- UI Layout (Image Context): {image_data_processed}
- User Interaction Elements (Action Data): {action_data_processed}
- Final Requirement to Validate: {requirements}

Instructions:
1. Each test case must follow a complete and realistic user flow from the beginning (such as login) to the final screen.
2. Cover all UI elements: inputs, buttons, dropdowns, etc.
3. Include a variety of test types: positive, negative, boundary, edge, retry.
4. Use orthogonal array/pairwise testing for coverage.

Output Format:
- Markdown table:
  | Test Case Name | Step Number | Test Step Description | Test Step Expected Result | Status | Type |
- Status = "New", Type = "Manual"
- Each case has 2–6 steps
- 15–20 full test cases
- No summaries or extra text""",
        "description": "Prompt used to generate the test cases with new version"
    }
]

from handler import bulk_add_prompts
bulk_add_prompts(prompt_list, created_by="sathanantham")
