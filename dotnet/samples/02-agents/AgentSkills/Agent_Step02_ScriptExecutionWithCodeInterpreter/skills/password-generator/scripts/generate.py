# Password generator script
# Usage: Adjust 'length' as needed, then run

import random
import string

length = 16  # desired length

pool = string.ascii_lowercase + string.ascii_uppercase + string.digits + string.punctuation
password = "".join(random.SystemRandom().choice(pool) for _ in range(length))
print(f"Generated password ({length} chars): {password}")
