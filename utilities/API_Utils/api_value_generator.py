"""
Named value generators for API request data.

A request can ask for a fresh fake value by name — ``$randomtext$``,
``$randommobile$``, ``$randomdob$`` — anywhere a ``${var}`` works: endpoint,
headers, path/query params, JSON payload, form fields. The key between the two
'$' is looked up in GENERATORS below and the returned value is substituted at
send time, so every run sends distinct data and a "create" API stops failing on
duplicate-record checks.

Kept in its own module rather than inside api_context so that adding test data
never means touching the resolver: write a function, register it in GENERATORS,
done. api_context imports this and calls generate() / has().

Lookup is forgiving — case, '_' and '-' are ignored — so ``$randomDOB$``,
``$random_dob$`` and ``$randomdob$`` are the same key.

Every generator takes one optional argument string, written in brackets before
the closing '$': ``$randomint(1,99)$``, ``$randomtext(3)$``,
``$randomdob(%d/%m/%Y)$``. The argument is always optional — a bare
``$randomint$`` uses the generator's own default.

Values keep their natural Python type. A cell that is *exactly* one placeholder
is substituted as that type (``"age": "$randomage$"`` sends the number 34, not
"34"); a placeholder inside a longer string is interpolated as text
(``"QA $randomfirstname$"``).
"""

import random
import string
import uuid
from datetime import datetime, timedelta

# ----------------------------------------------------------------------
# word pools — small on purpose: enough variety for unique values per run,
# not a locale database. Reach for Faker if real locale data is ever needed.
# ----------------------------------------------------------------------
FIRST_NAMES = [
    "Aarav", "Ananya", "Rohan", "Meera", "Kiran", "Priya", "Arjun", "Divya",
    "Vikram", "Nisha", "Rahul", "Sneha", "Karthik", "Anita", "Suresh", "Lakshmi",
    "James", "Emma", "Liam", "Olivia", "Noah", "Sophia", "Ethan", "Mia",
]
LAST_NAMES = [
    "Sharma", "Iyer", "Patel", "Reddy", "Nair", "Gupta", "Menon", "Rao",
    "Kumar", "Chowdhury", "Desai", "Pillai", "Smith", "Johnson", "Williams",
    "Brown", "Garcia", "Miller", "Davis", "Wilson",
]
CITIES = [
    "Chennai", "Bengaluru", "Mumbai", "Hyderabad", "Pune", "Delhi", "Kochi",
    "Kolkata", "London", "Austin", "Berlin", "Toronto", "Singapore", "Sydney",
]
STATES = [
    "Tamil Nadu", "Karnataka", "Maharashtra", "Telangana", "Kerala",
    "West Bengal", "Gujarat", "Texas", "California", "Ontario",
]
COUNTRIES = [
    "India", "United States", "United Kingdom", "Germany", "Canada",
    "Australia", "Singapore", "Japan", "Brazil", "France",
]
STREETS = [
    "Anna Salai", "MG Road", "Park Street", "Ring Road", "Beach Avenue",
    "Hill View Lane", "Maple Street", "Oak Avenue", "Station Road",
]
COMPANIES = [
    "Tiger Analytics", "Northwind Traders", "Acme Corp", "Globex", "Initech",
    "Umbrella Labs", "Contoso", "Fabrikam", "Stark Industries",
]
DEPARTMENTS = [
    "Quality Engineering", "Platform", "Data Science", "Finance", "Operations",
    "Customer Success", "Security", "Marketing",
]
JOB_TITLES = [
    "QA Engineer", "Test Architect", "Data Analyst", "Product Manager",
    "SRE", "Business Analyst", "Automation Lead", "Delivery Manager",
]
EMAIL_DOMAINS = ["example.com", "mailinator.com", "testmail.io", "qa-sandbox.net"]
LOREM = (
    "validate payload response latency schema endpoint contract regression "
    "coverage assertion payload gateway throughput baseline sandbox fixture "
    "sample record request handler token session"
).split()
CURRENCIES = ["USD", "INR", "EUR", "GBP", "SGD", "AUD"]
STATUSES = ["ACTIVE", "INACTIVE", "PENDING", "APPROVED", "REJECTED", "DRAFT"]
GENDERS = ["Male", "Female", "Other"]


# ----------------------------------------------------------------------
# argument parsing
# ----------------------------------------------------------------------
def _tokens(args):
    """The comma-separated pieces of an argument string, quotes stripped."""
    if not args:
        return []
    return [t.strip().strip('"').strip("'") for t in str(args).split(",") if t.strip()]


def _ints(args):
    """Only the numeric arguments — lets format and range share one arg list."""
    out = []
    for token in _tokens(args):
        try:
            out.append(int(token))
        except ValueError:
            continue
    return out


def _fmt(args, default):
    """The first strftime-looking argument, e.g. '%d/%m/%Y'."""
    for token in _tokens(args):
        if "%" in token:
            return token
    return default


def _range(args, low, high):
    """(low, high) from 0, 1 or 2 numeric arguments."""
    nums = _ints(args)
    if len(nums) == 1:
        return low, nums[0]
    if len(nums) >= 2:
        return nums[0], nums[1]
    return low, high


def _digits(count):
    return "".join(random.choice(string.digits) for _ in range(count))


def _letters(count, upper=True):
    pool = string.ascii_uppercase if upper else string.ascii_lowercase
    return "".join(random.choice(pool) for _ in range(count))


# ----------------------------------------------------------------------
# text
# ----------------------------------------------------------------------
def _random_text(args):
    """$randomtext$ -> a few words. $randomtext(3)$ -> exactly 3 words."""
    count = (_ints(args) or [5])[0]
    count = max(1, min(count, 200))
    words = [random.choice(LOREM) for _ in range(count)]
    return " ".join(words).capitalize()


def _random_sentence(args):
    return _random_text(args or "8").rstrip(".") + "."


def _random_paragraph(args):
    count = (_ints(args) or [3])[0]
    return " ".join(_random_sentence("10") for _ in range(max(1, min(count, 20))))


def _random_string(args):
    """Lowercase alphanumeric of the given length (default 8)."""
    length = max(1, min((_ints(args) or [8])[0], 4096))
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def _random_alpha(args):
    length = max(1, min((_ints(args) or [8])[0], 4096))
    return "".join(random.choice(string.ascii_letters) for _ in range(length))


def _random_word(args):
    return random.choice(LOREM)


# ----------------------------------------------------------------------
# people
# ----------------------------------------------------------------------
def _random_first_name(args):
    return random.choice(FIRST_NAMES)


def _random_last_name(args):
    return random.choice(LAST_NAMES)


def _random_name(args):
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def _random_username(args):
    return f"{random.choice(FIRST_NAMES).lower()}.{random.choice(LAST_NAMES).lower()}{random.randint(1, 999)}"


def _random_email(args):
    """$randomemail$ -> unique address. $randomemail(tigeranalytics.com)$ -> own domain."""
    domain = next((t for t in _tokens(args) if "." in t), None) or random.choice(EMAIL_DOMAINS)
    return f"{_random_username(None)}@{domain}"


def _random_password(args):
    """Mixed-case, digit and symbol — satisfies the usual signup policy."""
    length = max(8, min((_ints(args) or [12])[0], 128))
    pools = [string.ascii_uppercase, string.ascii_lowercase, string.digits, "!@#$%*?"]
    chars = [random.choice(pool) for pool in pools]
    everything = "".join(pools)
    chars += [random.choice(everything) for _ in range(length - len(chars))]
    random.shuffle(chars)
    return "".join(chars)


def _random_gender(args):
    return random.choice(GENDERS)


def _random_age(args):
    low, high = _range(args, 18, 70)
    return random.randint(low, high)


# ----------------------------------------------------------------------
# phone
# ----------------------------------------------------------------------
def _random_mobile(args):
    """
    A 10-digit Indian mobile number (first digit 6-9, which the usual
    validation regex insists on). $randommobile(+91)$ prefixes a country code.
    """
    prefix = next((t for t in _tokens(args) if not t.isdigit() or t.startswith("+")), "")
    return f"{prefix}{random.choice('6789')}{_digits(9)}"


def _random_phone(args):
    """Landline-style, with separators — for fields that accept formatted input."""
    return f"+{random.randint(1, 99)}-{_digits(3)}-{_digits(3)}-{_digits(4)}"


# ----------------------------------------------------------------------
# dates
# ----------------------------------------------------------------------
def _shift_years(years):
    """Same calendar date N years back, Feb-29 safe."""
    today = datetime.now()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


def _random_dob(args):
    """
    A date of birth. Numeric arguments set the age range, a '%' argument sets
    the output format, and both can be given together:

        $randomdob$                    -> 1987-04-23      (age 18-75)
        $randomdob(21,45)$             -> 1996-11-02
        $randomdob(%d/%m/%Y)$          -> 23/04/1987
        $randomdob(21,45,%d-%m-%Y)$    -> 02-11-1996
    """
    low, high = _range(args, 18, 75)
    if low > high:
        low, high = high, low
    oldest = _shift_years(high)
    youngest = _shift_years(low)
    span = (youngest - oldest).days or 1
    born = oldest + timedelta(days=random.randint(0, span))
    return born.strftime(_fmt(args, "%Y-%m-%d"))


def _random_date(args):
    """Any date within +/- 5 years of today. $randomdate(%d-%b-%Y)$ to format."""
    offset = random.randint(-1825, 1825)
    return (datetime.now() + timedelta(days=offset)).strftime(_fmt(args, "%Y-%m-%d"))


def _random_past_date(args):
    """$randompastdate$ -> up to a year ago. $randompastdate(30)$ -> within 30 days."""
    window = (_ints(args) or [365])[0]
    return (datetime.now() - timedelta(days=random.randint(1, max(1, window)))).strftime(
        _fmt(args, "%Y-%m-%d"))


def _random_future_date(args):
    window = (_ints(args) or [365])[0]
    return (datetime.now() + timedelta(days=random.randint(1, max(1, window)))).strftime(
        _fmt(args, "%Y-%m-%d"))


def _random_datetime(args):
    offset = random.randint(-365, 365)
    moment = datetime.now() + timedelta(
        days=offset, hours=random.randint(0, 23), minutes=random.randint(0, 59))
    return moment.strftime(_fmt(args, "%Y-%m-%dT%H:%M:%S"))


def _random_time(args):
    return f"{random.randint(0, 23):02d}:{random.randint(0, 59):02d}:{random.randint(0, 59):02d}"


def _random_epoch(args):
    """Unix seconds — 'ms' as the argument gives milliseconds."""
    stamp = (datetime.now() + timedelta(days=random.randint(-365, 365))).timestamp()
    if "ms" in [t.lower() for t in _tokens(args)]:
        return int(stamp * 1000)
    return int(stamp)


# ----------------------------------------------------------------------
# numbers
# ----------------------------------------------------------------------
def _random_int(args):
    low, high = _range(args, 1, 1_000_000)
    if low > high:
        low, high = high, low
    return random.randint(low, high)


def _random_decimal(args):
    """$randomdecimal$ -> 2dp. $randomdecimal(1,100,3)$ -> low, high, places."""
    nums = _ints(args)
    low, high = (nums + [1, 10_000])[:2] if len(nums) >= 2 else (1, 10_000)
    places = nums[2] if len(nums) >= 3 else 2
    return round(random.uniform(low, high), max(0, min(places, 8)))


def _random_amount(args):
    return _random_decimal(args or "1,100000,2")


def _random_percent(args):
    return round(random.uniform(0, 100), 2)


def _random_boolean(args):
    return random.choice([True, False])


def _random_currency(args):
    return random.choice(CURRENCIES)


def _random_status(args):
    return random.choice(STATUSES)


# ----------------------------------------------------------------------
# identifiers
# ----------------------------------------------------------------------
def _random_uuid(args):
    return str(uuid.uuid4())


def _random_id(args):
    """Short unique-per-run id, safe to embed in a name."""
    return f"{int(datetime.now().timestamp())}{random.randint(100, 999)}"


def _random_pan(args):
    """Indian PAN shape: AAAAA9999A. Structurally valid, not a real PAN."""
    return f"{_letters(5)}{_digits(4)}{_letters(1)}"


def _random_gst(args):
    """Indian GSTIN shape: 2-digit state code + PAN + entity digit + 'Z' + check char."""
    return f"{random.randint(1, 37):02d}{_random_pan(None)}{random.randint(1, 9)}Z{_letters(1)}"


def _random_ifsc(args):
    return f"{_letters(4)}0{_digits(6)}"


def _random_account_number(args):
    length = max(6, min((_ints(args) or [12])[0], 20))
    return _digits(length)


def _luhn_check_digit(number):
    total, double = 0, True
    for char in reversed(number):
        digit = int(char)
        if double:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
        double = not double
    return str((10 - total % 10) % 10)


def _random_credit_card(args):
    """
    A 16-digit test card number that passes a Luhn check, built on the reserved
    '4111' test prefix so it can never collide with a real issued card.
    """
    body = "4111" + _digits(11)
    return body + _luhn_check_digit(body)


# ----------------------------------------------------------------------
# address & web
# ----------------------------------------------------------------------
def _random_city(args):
    return random.choice(CITIES)


def _random_state(args):
    return random.choice(STATES)


def _random_country(args):
    return random.choice(COUNTRIES)


def _random_pincode(args):
    return _digits(6)


def _random_zip(args):
    return _digits(5)


def _random_address(args):
    return f"{random.randint(1, 499)}, {random.choice(STREETS)}, {random.choice(CITIES)}"


def _random_company(args):
    return random.choice(COMPANIES)


def _random_department(args):
    return random.choice(DEPARTMENTS)


def _random_job_title(args):
    return random.choice(JOB_TITLES)


def _random_url(args):
    return f"https://www.{_random_string('6')}.{random.choice(['com', 'io', 'net'])}/{_random_word(None)}"


def _random_ipv4(args):
    return ".".join(str(random.randint(1, 254)) for _ in range(4))


def _random_mac(args):
    return ":".join(f"{random.randint(0, 255):02x}" for _ in range(6))


def _random_color(args):
    return "#" + "".join(random.choice("0123456789abcdef") for _ in range(6))


def _random_filename(args):
    extension = next((t for t in _tokens(args) if not t.isdigit()), "pdf").lstrip(".")
    return f"{_random_word(None)}_{_random_string('5')}.{extension}"


# ======================================================================
# the mapping — key -> generator
#
# Every function above takes one optional argument string. Add a new entry
# here and it is immediately usable as $key$ in any request; nothing in
# api_context or api_runner needs to change.
# ======================================================================
GENERATORS = {
    # text
    "randomtext": _random_text,
    "randomsentence": _random_sentence,
    "randomparagraph": _random_paragraph,
    "randomstring": _random_string,
    "randomalpha": _random_alpha,
    "randomword": _random_word,

    # people
    "randomname": _random_name,
    "randomfullname": _random_name,
    "randomfirstname": _random_first_name,
    "randomlastname": _random_last_name,
    "randomusername": _random_username,
    "randomemail": _random_email,
    "randompassword": _random_password,
    "randomgender": _random_gender,
    "randomage": _random_age,

    # phone
    "randommobile": _random_mobile,
    "randomphone": _random_phone,

    # dates
    "randomdob": _random_dob,
    "randomdate": _random_date,
    "randompastdate": _random_past_date,
    "randomfuturedate": _random_future_date,
    "randomdatetime": _random_datetime,
    "randomtime": _random_time,
    "randomepoch": _random_epoch,
    "randomtimestamp": _random_epoch,

    # numbers
    "randomint": _random_int,
    "randomnumber": _random_int,
    "randomdecimal": _random_decimal,
    "randomamount": _random_amount,
    "randompercent": _random_percent,
    "randomboolean": _random_boolean,
    "randomcurrency": _random_currency,
    "randomstatus": _random_status,

    # identifiers
    "randomuuid": _random_uuid,
    "randomguid": _random_uuid,
    "randomid": _random_id,
    "randompan": _random_pan,
    "randomgst": _random_gst,
    "randomifsc": _random_ifsc,
    "randomaccountnumber": _random_account_number,
    "randomcreditcard": _random_credit_card,

    # address & web
    "randomcity": _random_city,
    "randomstate": _random_state,
    "randomcountry": _random_country,
    "randompincode": _random_pincode,
    "randomzip": _random_zip,
    "randomaddress": _random_address,
    "randomcompany": _random_company,
    "randomdepartment": _random_department,
    "randomjobtitle": _random_job_title,
    "randomurl": _random_url,
    "randomip": _random_ipv4,
    "randomipv4": _random_ipv4,
    "randommac": _random_mac,
    "randomcolor": _random_color,
    "randomfilename": _random_filename,
}

# One-line description per key, shown in the UI help so a tester can see what
# is available without opening this file.
DESCRIPTIONS = {
    "randomtext": "Words of filler text — $randomtext(3)$ for a word count",
    "randomsentence": "One sentence of filler text",
    "randomparagraph": "Paragraphs of filler text — $randomparagraph(2)$",
    "randomstring": "Lowercase alphanumeric — $randomstring(12)$ for a length",
    "randomalpha": "Letters only — $randomalpha(6)$ for a length",
    "randomword": "A single word",
    "randomname": "Full name",
    "randomfullname": "Full name (alias of $randomname$)",
    "randomfirstname": "First name",
    "randomlastname": "Last name",
    "randomusername": "Unique username, e.g. priya.nair417",
    "randomemail": "Unique email — $randomemail(mydomain.com)$ for your own domain",
    "randompassword": "Password with upper, lower, digit and symbol — $randompassword(16)$",
    "randomgender": "Male / Female / Other",
    "randomage": "Age as a number — $randomage(21,60)$ for a range",
    "randommobile": "10-digit mobile starting 6-9 — $randommobile(+91)$ to add a country code",
    "randomphone": "Formatted phone number with separators",
    "randomdob": "Date of birth — $randomdob(21,45,%d/%m/%Y)$ sets age range and format",
    "randomdate": "A date within +/- 5 years — $randomdate(%d-%b-%Y)$ to format",
    "randompastdate": "A past date — $randompastdate(30)$ for within 30 days",
    "randomfuturedate": "A future date — $randomfuturedate(90)$ for within 90 days",
    "randomdatetime": "ISO date-time",
    "randomtime": "Time as HH:MM:SS",
    "randomepoch": "Unix seconds — $randomepoch(ms)$ for milliseconds",
    "randomtimestamp": "Unix seconds (alias of $randomepoch$)",
    "randomint": "Whole number — $randomint(1,999)$ for a range",
    "randomnumber": "Whole number (alias of $randomint$)",
    "randomdecimal": "Decimal — $randomdecimal(1,100,3)$ sets range and decimal places",
    "randomamount": "Money-shaped decimal with 2 places",
    "randompercent": "0-100 with 2 decimal places",
    "randomboolean": "true or false (a real JSON boolean)",
    "randomcurrency": "ISO currency code",
    "randomstatus": "ACTIVE / PENDING / APPROVED / …",
    "randomuuid": "UUID4",
    "randomguid": "UUID4 (alias of $randomuuid$)",
    "randomid": "Short id, unique within the run",
    "randompan": "Indian PAN shape AAAAA9999A (structurally valid, not real)",
    "randomgst": "Indian GSTIN shape",
    "randomifsc": "Bank IFSC shape",
    "randomaccountnumber": "Digits for an account number — $randomaccountnumber(16)$",
    "randomcreditcard": "16-digit Luhn-valid test card on the reserved 4111 prefix",
    "randomcity": "City name",
    "randomstate": "State / province",
    "randomcountry": "Country name",
    "randompincode": "6-digit postal code",
    "randomzip": "5-digit ZIP code",
    "randomaddress": "Single-line street address",
    "randomcompany": "Company name",
    "randomdepartment": "Department name",
    "randomjobtitle": "Job title",
    "randomurl": "https URL",
    "randomip": "IPv4 address",
    "randomipv4": "IPv4 address (alias of $randomip$)",
    "randommac": "MAC address",
    "randomcolor": "Hex colour, e.g. #3fa9c2",
    "randomfilename": "File name — $randomfilename(csv)$ for an extension",
}


# ----------------------------------------------------------------------
# lookup
# ----------------------------------------------------------------------
def normalise(key):
    """
    Fold a key to its canonical form.

    Case, '_' and '-' are ignored so a sheet written as $random_DOB$ finds the
    same generator as $randomdob$ — the keys are typed by hand into Excel cells
    and that inconsistency is not worth a failed run.
    """
    return "".join(ch for ch in str(key or "").lower() if ch.isalnum())


_LOOKUP = {normalise(key): fn for key, fn in GENERATORS.items()}


def has(key):
    """True if key names a generator."""
    return normalise(key) in _LOOKUP


def generate(key, args=None):
    """
    Produce a value for key.

    Raises KeyError for an unknown key — callers check has() first, and a
    resolver that leaves unknown $tokens$ alone never gets here.
    """
    fn = _LOOKUP[normalise(key)]
    return fn(args)


def available():
    """
    [(key, description, sample), ...] in declaration order, for the UI help
    table. The sample is generated live, so it always matches the code.
    """
    listing = []
    for key in GENERATORS:
        try:
            sample = generate(key)
        except Exception as exc:  # a broken generator must not break the page
            sample = f"<error: {exc}>"
        listing.append((key, DESCRIPTIONS.get(key, ""), sample))
    return listing
