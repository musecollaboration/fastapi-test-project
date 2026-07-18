from fastapi import FastAPI


app = FastAPI()


@app.get('/func1')
async def func1():
    return {'func1 message': 'OK'}


@app.get('/func2')
async def func2():
    return {'func2 message': 'OK'}


@app.get('/func3')
async def func3():
    return {'func3 message': 'OK'}
