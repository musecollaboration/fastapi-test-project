from fastapi import FastAPI


add = FastAPI()


@add.get('/')
async def root():
    return {'message': 'OK'}
