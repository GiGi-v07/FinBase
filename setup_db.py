"""
setup_db.py - one-time database setup for the FinanceDB project.

Run:  python setup_db.py

Steps
  1. CREATE DATABASE Financedb (if missing)
  2. DROP the project's tables (only the tables listed below) so the script can be re-run
  3. CREATE TABLE for every entity (primary keys, data types, CHECK / UNIQUE constraints)
  4. ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY for every relationship (with cascades)
  5. CREATE VIEW user_details (works out age from DOB, so age is never stored)
  6. Optionally load sample data
"""
import os
import subprocess
import sys

# Load local .env file if present (without external packages)
_env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_file):
    with open(_env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

MYSQL_PATH = os.environ.get("MYSQL_PATH", r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe")
DB_PASS = os.environ.get("DB_PASS", "")
DB_NAME = os.environ.get("DB_NAME", "Financedb")


def run(sql, use_db=True, label=""):
    """Run one SQL batch through mysql.exe. Stops the script if MySQL reports an error."""
    if use_db:
        cmd = f'"{MYSQL_PATH}" -u root -p"{DB_PASS}" -e "USE {DB_NAME}; {sql}"'
    else:
        cmd = f'"{MYSQL_PATH}" -u root -p"{DB_PASS}" -e "{sql}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    errors = [line for line in result.stderr.splitlines()
              if line.strip() and "Using a password" not in line]
    if result.returncode != 0:
        print(f"  [FAILED] {label}")
        print("          " + " ".join(errors))
        sys.exit(1)
    print(f"  [ OK ]   {label}")


# --------------------------------------------------------------------------
# 1. Tables (created first WITHOUT foreign keys; FKs are added with ALTER TABLE)
# --------------------------------------------------------------------------
CREATE_TABLES = [
    ("household",
     "CREATE TABLE household ("
     " household_Id INT AUTO_INCREMENT PRIMARY KEY,"
     " name VARCHAR(100) NOT NULL"
     ") ENGINE=InnoDB;"),

    ("company",
     "CREATE TABLE company ("
     " Company_Id INT AUTO_INCREMENT PRIMARY KEY,"
     " name VARCHAR(100) NOT NULL UNIQUE,"
     " industry VARCHAR(100) NULL"
     ") ENGINE=InnoDB;"),

    # Age is NOT stored - the user_details view works it out from DOB.
    ("user",
     "CREATE TABLE `user` ("
     " user_Id INT AUTO_INCREMENT PRIMARY KEY,"
     " name VARCHAR(100) NOT NULL,"
     " DOB DATE NOT NULL,"
     " household_Id INT NULL,"
     " Company_Id INT NULL"
     ") ENGINE=InnoDB;"),

    ("shares",
     "CREATE TABLE shares ("
     " share_Id INT AUTO_INCREMENT PRIMARY KEY,"
     " mkt_price DECIMAL(12,2) NOT NULL,"
     " Company_Id INT NOT NULL,"
     " CONSTRAINT chk_shares_price CHECK (mkt_price >= 0)"
     ") ENGINE=InnoDB;"),

    # Junction table for the M:N 'Owns' relationship (User <-> Shares)
    ("owns",
     "CREATE TABLE owns ("
     " user_Id INT NOT NULL,"
     " share_Id INT NOT NULL,"
     " PRIMARY KEY (user_Id, share_Id)"
     ") ENGINE=InnoDB;"),

    ("bank",
     "CREATE TABLE bank ("
     " Bank_Id INT AUTO_INCREMENT PRIMARY KEY,"
     " Name VARCHAR(100) NOT NULL,"
     " Branch_Code VARCHAR(20) NOT NULL,"
     " CONSTRAINT uq_bank_branch UNIQUE (Name, Branch_Code)"
     ") ENGINE=InnoDB;"),

    # Company_Id is UNIQUE -> the Company-Account relationship is 1:1
    ("account",
     "CREATE TABLE account ("
     " Acc_Id INT AUTO_INCREMENT PRIMARY KEY,"
     " balance DECIMAL(15,2) NOT NULL DEFAULT 0,"
     " Account_type ENUM('Savings','Current','Salary','Fixed Deposit','Business') NOT NULL,"
     " user_Id INT NULL,"
     " Company_Id INT NULL,"
     " Bank_Id INT NOT NULL,"
     " CONSTRAINT uq_account_company UNIQUE (Company_Id)"
     ") ENGINE=InnoDB;"),

    # Weak entity: it can't exist without its Account (NOT NULL FK + ON DELETE CASCADE)
    ("subscription",
     "CREATE TABLE subscription ("
     " Sub_Id INT AUTO_INCREMENT PRIMARY KEY,"
     " Acc_Id INT NOT NULL,"
     " Name VARCHAR(100) NOT NULL,"
     " Amount DECIMAL(10,2) NOT NULL,"
     " Bill_Cycle ENUM('Weekly','Monthly','Quarterly','Yearly') NOT NULL DEFAULT 'Monthly',"
     " CONSTRAINT chk_sub_amount CHECK (Amount >= 0)"
     ") ENGINE=InnoDB;"),

    ("category",
     "CREATE TABLE category ("
     " category_Id INT AUTO_INCREMENT PRIMARY KEY,"
     " name VARCHAR(50) NOT NULL UNIQUE"
     ") ENGINE=InnoDB;"),

    ("transaction",
     "CREATE TABLE `transaction` ("
     " transaction_Id INT AUTO_INCREMENT PRIMARY KEY,"
     " amount DECIMAL(12,2) NOT NULL,"
     " `Date` DATE NOT NULL,"
     " `type` ENUM('Credit','Debit') NOT NULL,"
     " Acc_Id INT NOT NULL,"
     " category_Id INT NULL,"
     " CONSTRAINT chk_txn_amount CHECK (amount > 0)"
     ") ENGINE=InnoDB;"),

    ("goal",
     "CREATE TABLE goal ("
     " Goal_Id INT AUTO_INCREMENT PRIMARY KEY,"
     " current_amt DECIMAL(12,2) NOT NULL DEFAULT 0,"
     " target_amt DECIMAL(12,2) NOT NULL,"
     " Acc_Id INT NOT NULL,"
     " category_Id INT NULL,"
     " CONSTRAINT chk_goal_target CHECK (target_amt > 0),"
     " CONSTRAINT chk_goal_current CHECK (current_amt >= 0)"
     ") ENGINE=InnoDB;"),
]

# --------------------------------------------------------------------------
# 2. Foreign keys (relationships from the ER diagram)
# --------------------------------------------------------------------------
FOREIGN_KEYS = [
    # User --lives in--> Household (N:1). Deleting a household keeps its users (FK set to NULL).
    ("user -> household (lives in)",
     "ALTER TABLE `user` ADD CONSTRAINT fk_user_household FOREIGN KEY (household_Id)"
     " REFERENCES household(household_Id) ON DELETE SET NULL ON UPDATE CASCADE;"),
    # User --employed by--> Company (N:1)
    ("user -> company (employs)",
     "ALTER TABLE `user` ADD CONSTRAINT fk_user_company FOREIGN KEY (Company_Id)"
     " REFERENCES company(Company_Id) ON DELETE SET NULL ON UPDATE CASCADE;"),
    # Shares --listed by--> Company (N:1). Deleting a company deletes its shares.
    ("shares -> company (listed by)",
     "ALTER TABLE shares ADD CONSTRAINT fk_shares_company FOREIGN KEY (Company_Id)"
     " REFERENCES company(Company_Id) ON DELETE CASCADE ON UPDATE CASCADE;"),
    # Owns (M:N junction)
    ("owns -> user",
     "ALTER TABLE owns ADD CONSTRAINT fk_owns_user FOREIGN KEY (user_Id)"
     " REFERENCES `user`(user_Id) ON DELETE CASCADE ON UPDATE CASCADE;"),
    ("owns -> shares",
     "ALTER TABLE owns ADD CONSTRAINT fk_owns_share FOREIGN KEY (share_Id)"
     " REFERENCES shares(share_Id) ON DELETE CASCADE ON UPDATE CASCADE;"),
    # Account --has--> User (N:1)
    ("account -> user (has)",
     "ALTER TABLE account ADD CONSTRAINT fk_account_user FOREIGN KEY (user_Id)"
     " REFERENCES `user`(user_Id) ON DELETE CASCADE ON UPDATE CASCADE;"),
    # Account --has--> Company (1:1 because of the UNIQUE constraint)
    ("account -> company (has, 1:1)",
     "ALTER TABLE account ADD CONSTRAINT fk_account_company FOREIGN KEY (Company_Id)"
     " REFERENCES company(Company_Id) ON DELETE CASCADE ON UPDATE CASCADE;"),
    # Account --managed by--> Bank (N:1). RESTRICT: a bank with accounts can't be deleted.
    ("account -> bank (managed by)",
     "ALTER TABLE account ADD CONSTRAINT fk_account_bank FOREIGN KEY (Bank_Id)"
     " REFERENCES bank(Bank_Id) ON DELETE RESTRICT ON UPDATE CASCADE;"),
    # Subscription (weak) --billed to--> Account
    ("subscription -> account (billed to)",
     "ALTER TABLE subscription ADD CONSTRAINT fk_sub_account FOREIGN KEY (Acc_Id)"
     " REFERENCES account(Acc_Id) ON DELETE CASCADE ON UPDATE CASCADE;"),
    # Transaction --records to--> Account, --has--> Category
    ("transaction -> account (records to)",
     "ALTER TABLE `transaction` ADD CONSTRAINT fk_txn_account FOREIGN KEY (Acc_Id)"
     " REFERENCES account(Acc_Id) ON DELETE CASCADE ON UPDATE CASCADE;"),
    ("transaction -> category (has)",
     "ALTER TABLE `transaction` ADD CONSTRAINT fk_txn_category FOREIGN KEY (category_Id)"
     " REFERENCES category(category_Id) ON DELETE SET NULL ON UPDATE CASCADE;"),
    # Goal --saving for--> Account, --has--> Category
    ("goal -> account (saving for)",
     "ALTER TABLE goal ADD CONSTRAINT fk_goal_account FOREIGN KEY (Acc_Id)"
     " REFERENCES account(Acc_Id) ON DELETE CASCADE ON UPDATE CASCADE;"),
    ("goal -> category (has)",
     "ALTER TABLE goal ADD CONSTRAINT fk_goal_category FOREIGN KEY (category_Id)"
     " REFERENCES category(category_Id) ON DELETE SET NULL ON UPDATE CASCADE;"),
]

# --------------------------------------------------------------------------
# 3. View - age is worked out when the data is read, never stored
# --------------------------------------------------------------------------
CREATE_VIEW = (
    "CREATE OR REPLACE VIEW user_details AS"
    " SELECT u.user_Id, u.name, u.DOB,"
    " TIMESTAMPDIFF(YEAR, u.DOB, CURDATE()) AS age,"
    " u.household_Id, h.name AS household_name,"
    " u.Company_Id, c.name AS company_name"
    " FROM `user` u"
    " LEFT JOIN household h ON h.household_Id = u.household_Id"
    " LEFT JOIN company c ON c.Company_Id = u.Company_Id;"
)

DROP_ALL = (
    "SET FOREIGN_KEY_CHECKS = 0;"
    " DROP VIEW IF EXISTS user_details;"
    " DROP TABLE IF EXISTS goal, `transaction`, category, subscription, account,"
    " bank, owns, shares, `user`, company, household;"
    " SET FOREIGN_KEY_CHECKS = 1;"
)

# --------------------------------------------------------------------------
# 4. Optional sample data
# --------------------------------------------------------------------------
SAMPLE_DATA = [
    ("household",
     "INSERT INTO household (household_Id, name) VALUES"
     " (1, 'Sharma Family'), (2, 'Mehta Residence');"),
    ("company",
     "INSERT INTO company (Company_Id, name, industry) VALUES"
     " (1, 'Infosys', 'IT Services'), (2, 'Tata Motors', 'Automobile'), (3, 'HDFC Ltd', 'Finance');"),
    ("user",
     "INSERT INTO `user` (user_Id, name, DOB, household_Id, Company_Id) VALUES"
     " (1, 'Shanil Shah', '2005-03-14', 1, 1), (2, 'Priya Sharma', '1978-07-22', 1, 2),"
     " (3, 'Rohan Mehta', '1990-11-02', 2, 3), (4, 'Anaya Mehta', '2012-01-30', 2, NULL);"),
    ("shares",
     "INSERT INTO shares (share_Id, mkt_price, Company_Id) VALUES"
     " (1, 1520.50, 1), (2, 1610.00, 1), (3, 945.75, 2), (4, 2780.00, 3);"),
    ("owns",
     "INSERT INTO owns (user_Id, share_Id) VALUES (1, 1), (1, 3), (2, 2), (2, 4), (3, 4);"),
    ("bank",
     "INSERT INTO bank (Bank_Id, Name, Branch_Code) VALUES"
     " (1, 'State Bank of India', 'SBIN0001'), (2, 'ICICI Bank', 'ICIC0042');"),
    ("account",
     "INSERT INTO account (Acc_Id, balance, Account_type, user_Id, Company_Id, Bank_Id) VALUES"
     " (1, 25000.00, 'Savings', 1, NULL, 1), (2, 182000.00, 'Salary', 2, NULL, 2),"
     " (3, 54000.00, 'Savings', 3, NULL, 1), (4, 9800000.00, 'Business', NULL, 1, 2),"
     " (5, 4500000.00, 'Business', NULL, 2, 1);"),
    ("subscription",
     "INSERT INTO subscription (Sub_Id, Acc_Id, Name, Amount, Bill_Cycle) VALUES"
     " (1, 1, 'Spotify', 119.00, 'Monthly'), (2, 2, 'Netflix', 649.00, 'Monthly'),"
     " (3, 3, 'Amazon Prime', 1499.00, 'Yearly'), (4, 1, 'Gym Membership', 2500.00, 'Quarterly');"),
    ("category",
     "INSERT INTO category (category_Id, name) VALUES"
     " (1, 'Groceries'), (2, 'Rent'), (3, 'Salary'), (4, 'Entertainment'), (5, 'Travel'), (6, 'Education');"),
    ("transaction",
     "INSERT INTO `transaction` (transaction_Id, amount, `Date`, `type`, Acc_Id, category_Id) VALUES"
     " (1, 85000.00, '2026-09-01', 'Credit', 2, 3), (2, 3200.00, '2026-09-03', 'Debit', 2, 1),"
     " (3, 649.00, '2026-09-05', 'Debit', 2, 4), (4, 15000.00, '2026-09-07', 'Debit', 3, 2),"
     " (5, 4200.00, '2026-09-12', 'Debit', 1, 6), (6, 2800.00, '2026-09-20', 'Debit', 3, 5),"
     " (7, 1800.00, '2026-10-02', 'Debit', 1, 1);"),
    ("goal",
     "INSERT INTO goal (Goal_Id, current_amt, target_amt, Acc_Id, category_Id) VALUES"
     " (1, 12000.00, 50000.00, 1, 5), (2, 60000.00, 200000.00, 2, 6), (3, 5000.00, 30000.00, 3, 4);"),
]


def main():
    print("FinanceDB setup")
    print(f"WARNING: this DROPS and recreates these tables in '{DB_NAME}':")
    print("  household, company, user, shares, owns, bank, account,")
    print("  subscription, category, transaction, goal (and view user_details)")
    if input("Type 'yes' to continue: ").strip().lower() != "yes":
        print("Aborted.")
        return
    seed = input("Insert sample data as well? [y/N]: ").strip().lower() == "y"

    print("\n[1] Database")
    run(f"CREATE DATABASE IF NOT EXISTS {DB_NAME};", use_db=False, label=f"CREATE DATABASE {DB_NAME}")

    print("\n[2] Dropping old project tables")
    run(DROP_ALL, label="DROP existing tables / view")

    print("\n[3] Creating tables")
    for name, sql in CREATE_TABLES:
        run(sql, label=f"CREATE TABLE {name}")

    print("\n[4] Adding foreign keys (ALTER TABLE)")
    for name, sql in FOREIGN_KEYS:
        run(sql, label=name)

    print("\n[5] Creating view")
    run(CREATE_VIEW, label="CREATE VIEW user_details (age from DOB)")

    if seed:
        print("\n[6] Sample data")
        for name, sql in SAMPLE_DATA:
            run(sql, label=f"INSERT INTO {name}")

    print("\nSetup complete. Start the web app with:  python app.py")


if __name__ == "__main__":
    main()

