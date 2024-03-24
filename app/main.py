import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import httpx
import base64
import asyncio

def load_api_keys():
    for key in API_KEYS:
        API_KEYS[key] = os.getenv(key)
        if API_KEYS[key] is None:
            raise Exception(f"Failed to load {key} from .env file")

PORT = os.getenv("PORT")
if not PORT:
    raise ValueError("PORT environment variable not set!")

API_KEYS = {
    "API_NINJAS_KEY": None,
    "UNSPLASH_API_KEY": None
}

API_ENDPOINTS = {
    "COUNTRIES_NOW_API_ENDPOINT_COUNTRIES": "https://countriesnow.space/api/v0.1/countries/iso",
    "API_NINJAS_CITY_API_ENDPOINT_CITIES": "https://api.api-ninjas.com/v1/city",
    "UNSPLASH_API_ENDPOINT_IMAGES": "https://api.unsplash.com/search/photos",
    "WIKIPEDIA_API_ENDPOINT_DESCRIPTION": "https://en.wikipedia.org/w/api.php",
    "DUCK_STATUS_CODE_API_ENDPOINT_STATUS_CODE_IMAGE": "https://httpducks.com"
}

ENTRIES_NUMBER = 3

load_api_keys()


async def get_countries():
    response = httpx.get(API_ENDPOINTS["COUNTRIES_NOW_API_ENDPOINT_COUNTRIES"])
    return response.json()["data"]

async def get_cities(country_code: str, cities_number: int = ENTRIES_NUMBER):
    print(f"[Fetch] Started fetching cities for country: {country_code}")
    
    params = {'country': country_code, 'limit': cities_number}
    headers = {"X-Api-Key": API_KEYS["API_NINJAS_KEY"]}
    
    response = httpx.get(API_ENDPOINTS["API_NINJAS_CITY_API_ENDPOINT_CITIES"], params=params, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Error occurred while fetching cities data: {response.text}")
    
    if not isinstance(response.json(), list):
        raise Exception(f"Unexpected response type: {type(response.json())}, expected: <class 'list'>")
    
    print(f"[Fetch] Finished fetching cities for country: {country_code}")
    return response.json()

async def get_city_description(city: str):
    print(f"[Fetch] Started fetching description for city: {city}")
    
    params = {
        "format": "json",
        "action": "query",
        "prop": "extracts",
        "exintro": "",
        "explaintext": "",
        "redirects": "1",
        "titles": city
    }
    
    response = httpx.get(API_ENDPOINTS["WIKIPEDIA_API_ENDPOINT_DESCRIPTION"], params=params)
    
    page_id = list(response.json()["query"]["pages"].keys())[0]
    
    print(f"[Fetch] Finished fetching description for city: {city}")
    return response.json()["query"]["pages"][page_id]["extract"]

async def get_city_images(country_name: str, city: str, image_number: int = ENTRIES_NUMBER):
    print(f"[Fetch] Started fetching images for city: {city}")
    
    params = {'query': f"{country_name} {city}", 'per_page': image_number}
    headers = {"Authorization": f"Client-ID {API_KEYS['UNSPLASH_API_KEY']}"}
    
    response = httpx.get(API_ENDPOINTS["UNSPLASH_API_ENDPOINT_IMAGES"], params=params, headers=headers)
    
    print(f"[Fetch] Finished fetching images for city: {city}")
    return [item["urls"]["small"] for item in response.json()["results"]]

async def get_status_code_image(status_code: int):
    response = httpx.get(f"{API_ENDPOINTS['DUCK_STATUS_CODE_API_ENDPOINT_STATUS_CODE_IMAGE']}/{status_code}.jpg")
    return base64.b64encode(response.content).decode()

async def get_city_data(country_name: str, city_name: str):
    # Get city images and description concurrently
    tasks = [get_city_images(country_name, city_name), get_city_description(city_name)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    if isinstance(results[0], Exception):
        raise Exception(f"Error occurred while fetching images for country {country_name}.")
    urls = results[0]

    if isinstance(results[1], Exception):
        raise Exception(f"Error occurred while fetching description for country {country_name}.")
    description = results[1]

    city_entry = {
        "city_name": city_name,
        "urls": urls,
        "description": description
    }
    return city_entry


app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    status_code_detail_map = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        500: "Internal Server Error"
    }
    try:
        error_image = await get_status_code_image(exc.status_code)
        image_data = f"data:image/jpeg;base64,{error_image}"
    except Exception:
        image_data = ""
    return templates.TemplateResponse("error.html", {"request": request, "code": exc.status_code, "code_detail": status_code_detail_map[exc.status_code], "message": exc.detail, "image": image_data}, status_code=exc.status_code)

@app.get("/", response_class=HTMLResponse)
async def render_form(request: Request):
    try:
        countries_data = await get_countries()
        countries = [item["name"] for item in countries_data]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error occurred while fetching countries list.")
    
    return templates.TemplateResponse("index.html", {"request": request, "PORT": PORT, "countries": countries})


@app.post("/gallery/countries/", response_class=HTMLResponse)
async def render_country_gallery(request: Request):  
    form_data = await request.form()
    country_name = form_data["country_name"]

    if not country_name:
        raise HTTPException(status_code=400, detail="Country name is missing.")

    # Get the country code
    try:
        countries_data = await get_countries()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error occurred while fetching iso2 code for country {country_name}.")
        
    country_code_list = [ item["Iso2"] for item in countries_data if item["name"] == country_name ]
    
    if not country_code_list:
        raise HTTPException(status_code=400, detail="Invalid country name provided.")
    
    country_code = country_code_list[0]

    # Get cities 
    try:
        cities_data = await get_cities(country_code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error occurred while fetching cities data for country {country_name}.")
    
    cities = [item["name"] for item in cities_data]
    
    # Get city data concurrently for all cities
    tasks = [get_city_data(country_name, city) for city in cities]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    cities_entries = []
    for result in results:
        if isinstance(result, Exception):
            raise HTTPException(status_code=500, detail=f"{str(result)}")
        cities_entries.append(result)
    
    return templates.TemplateResponse("response.html", {"request": request, "country_name": country_name, "cities_entries": cities_entries})
