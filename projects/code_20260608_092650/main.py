
import json
import os

def list_files(directory='.'):
    """列出目录中的所有文件，返回文件名和大小"""
    files = []
    for f in os.listdir(directory):
        if os.path.isfile(os.path.join(directory, f)):
            size = os.path.getsize(os.path.join(directory, f))
            files.append({'name': f, 'size': size})
    return sorted(files, key=lambda x: x['size'], reverse=True)

if __name__ == '__main__':
    files = list_files()
    print(json.dumps(files[:5], indent=2))
