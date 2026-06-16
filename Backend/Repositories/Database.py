from mysql import connector
import os


class Database:
    @staticmethod
    def __open_connection():
        try:
            db = connector.connect(
                option_files=os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "../config.ini")
                ),
                autocommit=False,
            )

            cursor = db.cursor(dictionary=True, buffered=True)
            return db, cursor

        except connector.Error as err:
            if err.errno == connector.errorcode.ER_ACCESS_DENIED_ERROR:
                print("Error: no access to the database. Check username/password.")
            elif err.errno == connector.errorcode.ER_BAD_DB_ERROR:
                print("Error: database not found. Check database name.")
            else:
                print("Database error:", err)

            return None, None

    @staticmethod
    def get_rows(sql_query, params=None):
        db, cursor = Database.__open_connection()

        if db is None or cursor is None:
            return None

        try:
            cursor.execute(sql_query, params)
            result = cursor.fetchall()
            return result

        except Exception as error:
            print("Database get_rows error:", error)
            return None

        finally:
            cursor.close()
            db.close()

    @staticmethod
    def get_one_row(sql_query, params=None):
        db, cursor = Database.__open_connection()

        if db is None or cursor is None:
            return None

        try:
            cursor.execute(sql_query, params)
            result = cursor.fetchone()
            return result

        except Exception as error:
            print("Database get_one_row error:", error)
            return None

        finally:
            cursor.close()
            db.close()

    @staticmethod
    def execute_sql(sql_query, params=None):
        db, cursor = Database.__open_connection()

        if db is None or cursor is None:
            return None

        try:
            cursor.execute(sql_query, params)
            db.commit()

            if cursor.lastrowid != 0:
                return cursor.lastrowid

            return cursor.rowcount

        except connector.Error as error:
            db.rollback()
            print("Database execute_sql error:", error)
            return None

        finally:
            cursor.close()
            db.close()