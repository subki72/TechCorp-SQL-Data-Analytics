PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Departments (
    department_id INTEGER PRIMARY KEY,
    department_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS Employees (
    employee_id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE,
    hire_date TEXT NOT NULL,
    department_id INTEGER NOT NULL,
    FOREIGN KEY (department_id) REFERENCES Departments(department_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS Projects (
    project_id INTEGER PRIMARY KEY,
    project_name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    budget REAL NOT NULL CHECK (budget >= 0),
    department_id INTEGER NOT NULL,
    FOREIGN KEY (department_id) REFERENCES Departments(department_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_employees_department_id
    ON Employees (department_id);

CREATE INDEX IF NOT EXISTS idx_employees_hire_date
    ON Employees (hire_date);

CREATE INDEX IF NOT EXISTS idx_projects_department_id
    ON Projects (department_id);

CREATE INDEX IF NOT EXISTS idx_projects_budget
    ON Projects (budget);
