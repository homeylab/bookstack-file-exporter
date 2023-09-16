from datetime import datetime

def generate_root_folder(base_folder_name: str) -> str:
    return base_folder_name + "_" + datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    pass