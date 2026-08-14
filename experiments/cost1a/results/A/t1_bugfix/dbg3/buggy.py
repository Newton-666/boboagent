def add(a, b):
    return a - b  # BUG: should be a + b

def main():
    print(add(2, 3))

if __name__ == '__main__':
    main()
