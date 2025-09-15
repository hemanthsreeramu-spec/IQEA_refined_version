import re

# AI response in markdown format
response_text = f"""### Evaluation of Test Cases Against Requirement

The requirement specifies the need to display current and past QCT records on the Business Activity tab of an account record, showing all relevant fields and providing clickable links for navigation. It also requires functionality validation for various scenarios, such as absence of QCT records and login/logout functionality. Below is the detailed breakdown of the test scenarios, their evaluation using applicable design techniques, and the overall accuracy.

---

| Scenario ID | Scenario Description                                     | Technique | Parameters / Factors                                                                                                   | Score | Gaps                                                                                 | Suggestions                                                                     |
|-------------|---------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------------------------------------|-------|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| 1           | User login with valid credentials                       | EP        | Valid credentials (username, password), invalid credentials (invalid username, invalid password)                       | 75    | Missing tests for invalid credentials, account lockout after failed attempts       | Add negative test cases for incorrect username/password and lockout scenarios  |
| 1           | User login with valid credentials                       | ST        | System state: logged out, logged in                                                                                   | 100   | None                                                                                | None                                                                           |
| 2           | Navigation to Business Activity tab                     | OAT       | Factors: Account with QCTs, account without QCTs; Actions: click on tab                                               | 100   | None                                                                                | None                                                                           |
| 2           | Navigation to Business Activity tab                     | EP        | Valid accounts (with QCTs, without QCTs), invalid accounts (nonexistent)                                               | 75    | Missing test: invalid account (e.g., typing non-existent account in search bar)   | Add test case for navigating to invalid/nonexistent accounts                  |
| 3           | QCT related list loading on Business Activity tab       | EP        | Valid data sets (QCT statuses: active/inactive; multiple records), invalid data sets (no QCTs)                        | 90    | None                                                                                | None                                                                           |
| 3           | QCT related list loading on Business Activity tab       | DT        | Conditions: Account with QCTs, no QCTs, large number of QCT records                                                   | 75    | Missing edge cases for performance (e.g., large data volumes, degraded load time) | Add performance tests for large QCT volume and validate load times            |
| 4           | Display of required fields in QCT related list          | EP        | Valid partitions (QCT records with all fields), invalid partitions (null/empty fields)                                | 80    | Missing validation for cases when fields are null or empty                        | Add null/empty field test cases for each field                                 |
| 4           | Display of required fields in QCT related list          | DT        | Conditions: Field missing in database, field present but data invalid                                                 | 80    | Missing boundary tests for string fields (length constraints)                     | Add tests for boundary conditions (e.g., very long/short names)               |
| 5           | Clickable link navigation to QCT page                   | DT        | Conditions: Functional link, broken/nonexistent link                                                                  | 60    | Missing test for broken link or invalid page scenario                             | Add negative test case for invalid/malfunctioning clickable links             |
| 5           | Clickable link navigation to QCT page                   | ST        | System state: QCT page loads correctly, navigation error                                                              | 100   | None                                                                                | None                                                                           |
| 6           | No QCT records are shown for account with no related QCTs | EP        | Valid scenario (account with no QCTs), invalid scenario (account with QCTs not linked properly in DB)                 | 80    | Missing DB integrity validation test (e.g., improperly linked QCT records)        | Add test cases for database linkage errors                                     |
| 7           | Negative test: QCT related list without logging in       | ST        | System state: logged out, unauthorized access attempt                                                                 | 100   | None                                                                                | None                                                                           |
| 8           | Verify logout functionality                              | ST        | System state: User logged in, user logged out                                                                         | 100   | None                                                                                | None                                                                           |

---

### Observations
1. **Technique Coverage**:
   - For simpler scenarios (e.g., login, logout), **EP** and **ST** techniques suffice.
   - Complex scenarios (e.g., QCT list loading, field validation) benefit from **OAT** and **DT** to cover all combinations and conditions.
   - Boundary and performance testing are underrepresented across scenarios.

2. **Key Gaps**:
   - No negative test cases for invalid credentials, field boundaries, or broken links.
   - Missing performance tests to validate behavior with large QCT datasets.
   - Absence of database integrity checks (e.g., incorrectly linked QCT records).

3. **Suggestions**:
   - Add boundary testing (e.g., string length, expiration dates).
   - Incorporate negative tests (e.g., invalid/missing data, broken links).
   - Include performance scenarios for large QCT volume and gradual load degradation.

---

### Overall Accuracy

The technique scores for each scenario are averaged to compute the overall accuracy:

| Scenario ID | Technique             | Score |
|-------------|-----------------------|-------|
| 1           | EP                   | 75    |
| 1           | ST                   | 100   |
| 2           | OAT                  | 100   |
| 2           | EP                   | 75    |
| 3           | EP                   | 90    |
| 3           | DT                   | 75    |
| 4           | EP                   | 80    |
| 4           | DT                   | 80    |
| 5           | DT                   | 60    |
| 5           | ST                   | 100   |
| 6           | EP                   | 80    |
| 7           | ST                   | 100   |
| 8           | ST                   | 100   |

#### Overall Accuracy: **85.83%**

---

### Conclusion

While the overall accuracy is satisfactory, addressing the identified gaps (e.g., negative testing, performance validation, and boundary conditions) can enhance the test suite's robustness and ensure comprehensive coverage."""

# Use regex to find the "Overall Accuracy" line
match = re.search(r"Overall Accuracy: \*\*(\d+\.?\d*)%", response_text)
if match:
    overall_accuracy = float(match.group(1))
else:
    # If not found, compute manually from the last "Score" table
    scores = re.findall(r"\|\s*\d+\s*\|\s*[A-Z]+\s*\|\s*(\d+)\s*\|", response_text)
    if scores:
        scores = [float(s) for s in scores]
        overall_accuracy = sum(scores) / len(scores)
    else:
        overall_accuracy = 0

overall_accuracy = overall_accuracy
return overall_accuracy


def accuracy_collect(response_text):
    match = re.search(r"Overall Accuracy: \*\*(\d+\.?\d*)%", response_text)
    if match:
        overall_accuracy = float(match.group(1))
    else:
        # If not found, compute manually from the last "Score" table
        scores = re.findall(r"\|\s*\d+\s*\|\s*[A-Z]+\s*\|\s*(\d+)\s*\|", response_text)
        if scores:
            scores = [float(s) for s in scores]
            overall_accuracy = sum(scores) / len(scores)
        else:
            overall_accuracy = 0

    overall_accuracy = overall_accuracy
    return overall_accuracy