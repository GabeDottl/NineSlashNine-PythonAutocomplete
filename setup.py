from setuptools import setup
# d = os.path.split(os.path.abspath(__file__))[0]
# packages = list(filter(lambda x: not os.path.isdir(x), [os.path.join(d, x) for x in os.listdir(d)]))

setup(
    name='autocomplete',
    version='0.1',
    description='The funniest joke in the world',
    url='http://github.com/storborg/funniest',
    author='Flying Circus',
    author_email='flyingcircus@example.com',
    license='MIT',
    packages=[
        'autocomplete'
    ],  #'naive_suggestion_sort', 'reverse_history', 'debug', 'code_understanding'],
    zip_safe=False)
