from .Database import Database


class DataRepository:
    @staticmethod
    def read_devices():
        sql = "SELECT * FROM devices ORDER BY device_id"
        return Database.get_rows(sql)

    @staticmethod
    def read_device_by_id(device_id):
        sql = "SELECT * FROM devices WHERE device_id = %s"
        params = [device_id]
        return Database.get_one_row(sql, params)

    @staticmethod
    def read_sensors():
        sql = "SELECT * FROM devices WHERE device_type = 'sensor' ORDER BY device_id"
        return Database.get_rows(sql)

    @staticmethod
    def read_actuators():
        sql = "SELECT * FROM devices WHERE device_type = 'actuator' ORDER BY device_id"
        return Database.get_rows(sql)

    @staticmethod
    def read_actions():
        sql = "SELECT * FROM actions ORDER BY action_id"
        return Database.get_rows(sql)

    @staticmethod
    def read_action_by_name(action_name):
        sql = "SELECT * FROM actions WHERE action_name = %s"
        params = [action_name]
        return Database.get_one_row(sql, params)

    @staticmethod
    def read_history(limit=50):
        sql = """
            SELECT 
                h.history_id,
                h.history_type,
                h.value_number,
                h.value_text,
                h.comment,
                h.created_at,
                d.device_id,
                d.name AS device_name,
                d.device_type,
                d.unit,
                a.action_id,
                a.action_name
            FROM history h
            JOIN devices d ON h.device_id = d.device_id
            LEFT JOIN actions a ON h.action_id = a.action_id
            ORDER BY h.created_at DESC
            LIMIT %s
        """
        params = [limit]
        return Database.get_rows(sql, params)

    @staticmethod
    def read_measurements(limit=50):
        sql = """
            SELECT 
                h.history_id,
                h.value_number,
                h.value_text,
                h.comment,
                h.created_at,
                d.name AS device_name,
                d.unit
            FROM history h
            JOIN devices d ON h.device_id = d.device_id
            WHERE h.history_type = 'measurement'
            ORDER BY h.created_at DESC
            LIMIT %s
        """
        params = [limit]
        return Database.get_rows(sql, params)

    @staticmethod
    def read_actuator_history(limit=50):
        sql = """
            SELECT 
                h.history_id,
                h.value_number,
                h.value_text,
                h.comment,
                h.created_at,
                d.name AS device_name,
                a.action_name
            FROM history h
            JOIN devices d ON h.device_id = d.device_id
            LEFT JOIN actions a ON h.action_id = a.action_id
            WHERE h.history_type = 'action'
            ORDER BY h.created_at DESC
            LIMIT %s
        """
        params = [limit]
        return Database.get_rows(sql, params)

    @staticmethod
    def create_measurement(device_id, value_number=None, value_text=None, comment=None):
        sql = """
            INSERT INTO history
            (device_id, action_id, history_type, value_number, value_text, comment)
            VALUES
            (%s, 1, 'measurement', %s, %s, %s)
        """
        params = [device_id, value_number, value_text, comment]
        return Database.execute_sql(sql, params)

    @staticmethod
    def create_action(device_id, action_id, value_number=None, value_text=None, comment=None):
        sql = """
            INSERT INTO history
            (device_id, action_id, history_type, value_number, value_text, comment)
            VALUES
            (%s, %s, 'action', %s, %s, %s)
        """
        params = [device_id, action_id, value_number, value_text, comment]
        return Database.execute_sql(sql, params)

    @staticmethod
    def read_measurements_by_device(device_id, limit=20):
        sql = """
            SELECT 
                h.history_id,
                h.value_number,
                h.value_text,
                h.comment,
                h.created_at,
                d.device_id,
                d.name AS device_name,
                d.unit
            FROM history h
            JOIN devices d ON h.device_id = d.device_id
            WHERE h.history_type = 'measurement'
            AND h.device_id = %s
            ORDER BY h.created_at DESC
            LIMIT %s
        """
        params = [device_id, limit]
        return Database.get_rows(sql, params)