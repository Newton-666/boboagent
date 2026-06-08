import unittest
import os
import json
import tempfile
import shutil
from unittest.mock import patch

# 假设被测试的代码在 module_name.py 中
# from module_name import list_files

# 为了测试，这里直接包含被测试函数
def list_files(directory='.'):
    """列出目录中的所有文件，返回文件名和大小"""
    files = []
    for f in os.listdir(directory):
        if os.path.isfile(os.path.join(directory, f)):
            size = os.path.getsize(os.path.join(directory, f))
            files.append({'name': f, 'size': size})
    return sorted(files, key=lambda x: x['size'], reverse=True)


class TestListFiles(unittest.TestCase):
    
    def setUp(self):
        # 创建临时目录用于测试
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
    
    def tearDown(self):
        # 恢复原目录并删除临时目录
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir)
    
    def create_test_file(self, filename, content=b''):
        """辅助方法：在测试目录中创建文件"""
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(content)
        return filepath
    
    def test_empty_directory(self):
        """测试空目录"""
        result = list_files()
        self.assertEqual(result, [])
    
    def test_single_file(self):
        """测试单个文件"""
        self.create_test_file('test.txt', b'hello')
        result = list_files()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'test.txt')
        self.assertEqual(result[0]['size'], 5)
    
    def test_multiple_files_sorted_by_size_descending(self):
        """测试多个文件按大小降序排列"""
        self.create_test_file('small.txt', b'a')
        self.create_test_file('medium.txt', b'hello')
        self.create_test_file('large.txt', b'this is a larger file')
        
        result = list_files()
        self.assertEqual(len(result), 3)
        # 检查降序排列
        sizes = [f['size'] for f in result]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        # 检查最大文件
        self.assertEqual(result[0]['name'], 'large.txt')
    
    def test_files_with_same_size(self):
        """测试相同大小的文件"""
        self.create_test_file('file1.txt', b'hello')
        self.create_test_file('file2.txt', b'world')
        
        result = list_files()
        self.assertEqual(len(result), 2)
        # 两个文件大小相同，排序稳定但顺序不确定，只检查大小
        for f in result:
            self.assertEqual(f['size'], 5)
    
    def test_ignores_directories(self):
        """测试忽略目录"""
        self.create_test_file('file.txt', b'data')
        os.makedirs('subdir')
        
        result = list_files()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'file.txt')
    
    def test_custom_directory(self):
        """测试指定目录"""
        sub_dir = os.path.join(self.test_dir, 'subdir')
        os.makedirs(sub_dir)
        filepath = os.path.join(sub_dir, 'test.txt')
        with open(filepath, 'w') as f:
            f.write('data')
        
        result = list_files(sub_dir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'test.txt')
        self.assertEqual(result[0]['size'], 4)
    
    def test_large_file(self):
        """测试大文件"""
        large_content = b'x' * 1000000  # 1MB
        self.create_test_file('large.bin', large_content)
        
        result = list_files()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['size'], 1000000)
    
    def test_hidden_files(self):
        """测试隐藏文件（以点开头的文件）"""
        self.create_test_file('.hidden', b'secret')
        self.create_test_file('visible.txt', b'hello')
        
        result = list_files()
        self.assertEqual(len(result), 2)
        names = [f['name'] for f in result]
        self.assertIn('.hidden', names)
        self.assertIn('visible.txt', names)
    
    def test_file_with_spaces_in_name(self):
        """测试文件名包含空格"""
        self.create_test_file('my file.txt', b'data')
        
        result = list_files()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'my file.txt')
    
    def test_empty_file(self):
        """测试空文件"""
        self.create_test_file('empty.txt')
        
        result = list_files()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['size'], 0)
    
    def test_nonexistent_directory_raises_error(self):
        """测试不存在的目录"""
        with self.assertRaises(FileNotFoundError):
            list_files('/nonexistent/path')
    
    def test_permission_denied(self):
        """测试无权限访问的目录（模拟）"""
        # 创建一个无权限的目录
        restricted_dir = os.path.join(self.test_dir, 'restricted')
        os.makedirs(restricted_dir)
        os.chmod(restricted_dir, 0o000)
        
        try:
            with self.assertRaises(PermissionError):
                list_files(restricted_dir)
        finally:
            os.chmod(restricted_dir, 0o755)  # 恢复权限以便清理
    
    def test_default_directory_is_current(self):
        """测试默认参数使用当前目录"""
        self.create_test_file('test.txt', b'data')
        result_default = list_files()
        result_explicit = list_files('.')
        self.assertEqual(result_default, result_explicit)
    
    def test_main_block(self):
        """测试 __main__ 块（通过模拟）"""
        self.create_test_file('a.txt', b'small')
        self.create_test_file('b.txt', b'medium data')
        self.create_test_file('c.txt', b'large data here')
        
        # 模拟 __main__ 执行
        files = list_files()
        output = json.dumps(files[:5], indent=2)
        parsed = json.loads(output)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]['name'], 'c.txt')  # 最大文件


if __name__ == '__main__':
    unittest.main()