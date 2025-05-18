import sys
print("Python path:", sys.path)

try:
    import core
    print("core module imported successfully")
    print("core module path:", core.__file__)
    
    try:
        from core import database
        print("core.database module imported successfully")
        print("database module path:", database.__file__)
        
        try:
            from core.database import get_db
            print("get_db function imported successfully")
        except ImportError as e:
            print("Error importing get_db:", e)
    except ImportError as e:
        print("Error importing core.database:", e)
except ImportError as e:
    print("Error importing core:", e)