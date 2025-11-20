# Copyright (c) Microsoft. All rights reserved.

import json
from datetime import datetime
from typing import Annotated

from agent_framework import ai_function
from pydantic import Field

# --- Travel Planning Tools ---
# Note: These are mock tools for demonstration purposes. They return simulated data
# and do not make real API calls or bookings.


# Mock hotel search tool
@ai_function(name="search_hotels", description="Search for available hotels based on location and dates.")
def search_hotels(
    location: Annotated[str, Field(description="City or region to search for hotels.")],
    check_in: Annotated[str, Field(description="Check-in date (e.g., 'December 15, 2025').")],
    check_out: Annotated[str, Field(description="Check-out date (e.g., 'December 18, 2025').")],
    guests: Annotated[int, Field(description="Number of guests.")] = 2,
) -> str:
    """Search for available hotels based on location and dates.
    
    Returns:
        JSON string containing search results with hotel details including name, rating,
        price, distance to landmarks, amenities, and availability.
    """
    # Specific mock data for Paris December 15-18, 2025
    if "paris" in location.lower():
        mock_hotels = [
            {
                "name": "Hotel Eiffel Trocadéro",
                "rating": 4.6,
                "price_per_night": "$185",
                "total_price": "$555 for 3 nights",
                "distance_to_eiffel_tower": "0.3 miles",
                "amenities": ["WiFi", "Breakfast", "Eiffel Tower View", "Concierge"],
                "availability": "Available",
                "address": "35 Rue Benjamin Franklin, 16th arr., Paris"
            },
            {
                "name": "Mercure Paris Centre Tour Eiffel",
                "rating": 4.4,
                "price_per_night": "$220",
                "total_price": "$660 for 3 nights",
                "distance_to_eiffel_tower": "0.5 miles",
                "amenities": ["WiFi", "Restaurant", "Bar", "Gym", "Air Conditioning"],
                "availability": "Available",
                "address": "20 Rue Jean Rey, 15th arr., Paris"
            },
            {
                "name": "Pullman Paris Tour Eiffel",
                "rating": 4.7,
                "price_per_night": "$280",
                "total_price": "$840 for 3 nights",
                "distance_to_eiffel_tower": "0.2 miles",
                "amenities": ["WiFi", "Spa", "Gym", "Restaurant", "Rooftop Bar", "Concierge"],
                "availability": "Limited",
                "address": "18 Avenue de Suffren, 15th arr., Paris"
            }
        ]
    else:
        mock_hotels = [
            {
                "name": "Grand Plaza Hotel",
                "rating": 4.5,
                "price_per_night": "$150",
                "amenities": ["WiFi", "Pool", "Gym", "Restaurant"],
                "availability": "Available"
            }
        ]
    
    return json.dumps({
        "location": location,
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests,
        "hotels_found": len(mock_hotels),
        "hotels": mock_hotels,
        "note": "Hotel search results matching your query"
    })


# Mock hotel details tool
@ai_function(name="get_hotel_details", description="Get detailed information about a specific hotel.")
def get_hotel_details(
    hotel_name: Annotated[str, Field(description="Name of the hotel to get details for.")],
) -> str:
    """Get detailed information about a specific hotel.
    
    Returns:
        JSON string containing detailed hotel information including description,
        check-in/out times, cancellation policy, reviews, and nearby attractions.
    """
    hotel_details = {
        "Hotel Eiffel Trocadéro": {
            "description": "Charming boutique hotel with stunning Eiffel Tower views from select rooms. Perfect for couples and families.",
            "check_in_time": "3:00 PM",
            "check_out_time": "11:00 AM",
            "cancellation_policy": "Free cancellation up to 24 hours before check-in",
            "reviews": {
                "total": 1247,
                "recent_comments": [
                    "Amazing location! Walked to Eiffel Tower in 5 minutes.",
                    "Staff was incredibly helpful with restaurant recommendations.",
                    "Rooms are cozy and clean with great views."
                ]
            },
            "nearby_attractions": ["Eiffel Tower (0.3 mi)", "Trocadéro Gardens (0.2 mi)", "Seine River (0.4 mi)"]
        },
        "Mercure Paris Centre Tour Eiffel": {
            "description": "Modern hotel with contemporary rooms and excellent dining options. Close to metro stations.",
            "check_in_time": "2:00 PM",
            "check_out_time": "12:00 PM",
            "cancellation_policy": "Free cancellation up to 48 hours before check-in",
            "reviews": {
                "total": 2156,
                "recent_comments": [
                    "Great value for money, clean and comfortable.",
                    "Restaurant had excellent French cuisine.",
                    "Easy access to public transportation."
                ]
            },
            "nearby_attractions": ["Eiffel Tower (0.5 mi)", "Champ de Mars (0.4 mi)", "Les Invalides (0.8 mi)"]
        },
        "Pullman Paris Tour Eiffel": {
            "description": "Luxury hotel offering panoramic views, upscale amenities, and exceptional service. Ideal for a premium experience.",
            "check_in_time": "3:00 PM",
            "check_out_time": "12:00 PM",
            "cancellation_policy": "Free cancellation up to 72 hours before check-in",
            "reviews": {
                "total": 3421,
                "recent_comments": [
                    "Rooftop bar has the best Eiffel Tower views in Paris!",
                    "Luxurious rooms with every amenity you could want.",
                    "Worth the price for the location and service."
                ]
            },
            "nearby_attractions": ["Eiffel Tower (0.2 mi)", "Seine River Cruise Dock (0.3 mi)", "Trocadéro (0.5 mi)"]
        }
    }
    
    details = hotel_details.get(hotel_name, {
        "name": hotel_name,
        "description": "Comfortable hotel with modern amenities",
        "check_in_time": "3:00 PM",
        "check_out_time": "11:00 AM",
        "cancellation_policy": "Standard cancellation policy applies",
        "reviews": {"total": 0, "recent_comments": []},
        "nearby_attractions": []
    })
    
    return json.dumps({
        "hotel_name": hotel_name,
        "details": details
    })


# Mock flight search tool
@ai_function(name="search_flights", description="Search for available flights between two locations.")
def search_flights(
    origin: Annotated[str, Field(description="Departure airport or city (e.g., 'JFK' or 'New York').")],
    destination: Annotated[str, Field(description="Arrival airport or city (e.g., 'CDG' or 'Paris').")],
    departure_date: Annotated[str, Field(description="Departure date (e.g., 'December 15, 2025').")],
    return_date: Annotated[str | None, Field(description="Return date (e.g., 'December 18, 2025').")] = None,
    passengers: Annotated[int, Field(description="Number of passengers.")] = 1,
) -> str:
    """Search for available flights between two locations.
    
    Returns:
        JSON string containing flight search results with details including flight numbers,
        airlines, departure/arrival times, prices, durations, and baggage allowances.
    """
    # Specific mock data for JFK to Paris December 15-18, 2025
    if "jfk" in origin.lower() or "new york" in origin.lower():
        if "paris" in destination.lower() or "cdg" in destination.lower():
            mock_flights = [
                {
                    "outbound": {
                        "flight_number": "AF007",
                        "airline": "Air France",
                        "departure": "December 15, 2025 at 6:30 PM",
                        "arrival": "December 16, 2025 at 8:15 AM",
                        "duration": "7h 45m",
                        "aircraft": "Boeing 777-300ER",
                        "class": "Economy",
                        "price": "$520"
                    },
                    "return": {
                        "flight_number": "AF008",
                        "airline": "Air France",
                        "departure": "December 18, 2025 at 11:00 AM",
                        "arrival": "December 18, 2025 at 2:15 PM",
                        "duration": "8h 15m",
                        "aircraft": "Airbus A350-900",
                        "class": "Economy",
                        "price": "Included"
                    },
                    "total_price": "$520",
                    "stops": "Nonstop",
                    "baggage": "1 checked bag included"
                },
                {
                    "outbound": {
                        "flight_number": "DL264",
                        "airline": "Delta",
                        "departure": "December 15, 2025 at 10:15 PM",
                        "arrival": "December 16, 2025 at 12:05 PM",
                        "duration": "7h 50m",
                        "aircraft": "Airbus A330-900neo",
                        "class": "Economy",
                        "price": "$485"
                    },
                    "return": {
                        "flight_number": "DL265",
                        "airline": "Delta",
                        "departure": "December 18, 2025 at 1:45 PM",
                        "arrival": "December 18, 2025 at 5:00 PM",
                        "duration": "8h 15m",
                        "aircraft": "Airbus A330-900neo",
                        "class": "Economy",
                        "price": "Included"
                    },
                    "total_price": "$485",
                    "stops": "Nonstop",
                    "baggage": "1 checked bag included"
                },
                {
                    "outbound": {
                        "flight_number": "UA57",
                        "airline": "United Airlines",
                        "departure": "December 15, 2025 at 5:00 PM",
                        "arrival": "December 16, 2025 at 6:50 AM",
                        "duration": "7h 50m",
                        "aircraft": "Boeing 767-400ER",
                        "class": "Economy",
                        "price": "$560"
                    },
                    "return": {
                        "flight_number": "UA58",
                        "airline": "United Airlines",
                        "departure": "December 18, 2025 at 9:30 AM",
                        "arrival": "December 18, 2025 at 12:45 PM",
                        "duration": "8h 15m",
                        "aircraft": "Boeing 787-10",
                        "class": "Economy",
                        "price": "Included"
                    },
                    "total_price": "$560",
                    "stops": "Nonstop",
                    "baggage": "1 checked bag included"
                }
            ]
        else:
            mock_flights = [{"flight_number": "XX123", "airline": "Generic Air", "price": "$400", "note": "Generic route"}]
    else:
        mock_flights = [
            {
                "outbound": {
                    "flight_number": "AA123",
                    "airline": "Generic Airlines",
                    "departure": f"{departure_date} at 9:00 AM",
                    "arrival": f"{departure_date} at 2:30 PM",
                    "duration": "5h 30m",
                    "class": "Economy",
                    "price": "$350"
                },
                "total_price": "$350",
                "stops": "Nonstop"
            }
        ]
    
    return json.dumps({
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "return_date": return_date,
        "passengers": passengers,
        "flights_found": len(mock_flights),
        "flights": mock_flights,
        "note": "Flight search results for JFK to Paris CDG"
    })


# Mock flight details tool
@ai_function(name="get_flight_details", description="Get detailed information about a specific flight.")
def get_flight_details(
    flight_number: Annotated[str, Field(description="Flight number (e.g., 'AF007' or 'DL264').")],
) -> str:
    """Get detailed information about a specific flight.
    
    Returns:
        JSON string containing detailed flight information including airline, aircraft type,
        departure/arrival airports and times, gates, terminals, duration, and amenities.
    """
    mock_details = {
        "flight_number": flight_number,
        "airline": "Sky Airways",
        "aircraft": "Boeing 737-800",
        "departure": {
            "airport": "JFK International Airport",
            "terminal": "Terminal 4",
            "gate": "B23",
            "time": "08:00 AM"
        },
        "arrival": {
            "airport": "Charles de Gaulle Airport",
            "terminal": "Terminal 2E",
            "gate": "K15",
            "time": "11:30 AM local time"
        },
        "duration": "3h 30m",
        "baggage_allowance": {
            "carry_on": "1 bag (10kg)",
            "checked": "1 bag (23kg)"
        },
        "amenities": ["WiFi", "In-flight entertainment", "Meals included"]
    }
    
    return json.dumps({
        "flight_details": mock_details
    })


# Mock activity search tool
@ai_function(name="search_activities", description="Search for available activities and attractions at a destination.")
def search_activities(
    location: Annotated[str, Field(description="City or region to search for activities.")],
    date: Annotated[str | None, Field(description="Date for the activity (e.g., 'December 16, 2025').")] = None,
    category: Annotated[str | None, Field(description="Activity category (e.g., 'Sightseeing', 'Culture', 'Culinary').")] = None,
) -> str:
    """Search for available activities and attractions at a destination.
    
    Returns:
        JSON string containing activity search results with details including name, category,
        duration, price, rating, description, availability, and booking requirements.
    """
    # Specific mock data for Paris activities
    if "paris" in location.lower():
        all_activities = [
            {
                "name": "Eiffel Tower Summit Access",
                "category": "Sightseeing",
                "duration": "2-3 hours",
                "price": "$35",
                "rating": 4.8,
                "description": "Skip-the-line access to all three levels including the summit. Best views of Paris!",
                "availability": "Daily 9:30 AM - 11:00 PM",
                "best_time": "Early morning or sunset",
                "booking_required": True
            },
            {
                "name": "Louvre Museum Guided Tour",
                "category": "Sightseeing",
                "duration": "3 hours",
                "price": "$55",
                "rating": 4.7,
                "description": "Expert-guided tour covering masterpieces including Mona Lisa and Venus de Milo.",
                "availability": "Daily except Tuesdays, 9:00 AM entry",
                "best_time": "Morning entry recommended",
                "booking_required": True
            },
            {
                "name": "Seine River Cruise",
                "category": "Sightseeing",
                "duration": "1 hour",
                "price": "$18",
                "rating": 4.6,
                "description": "Scenic cruise past Notre-Dame, Eiffel Tower, and historic bridges.",
                "availability": "Every 30 minutes, 10:00 AM - 10:00 PM",
                "best_time": "Evening for illuminated monuments",
                "booking_required": False
            },
            {
                "name": "Musée d'Orsay Visit",
                "category": "Culture",
                "duration": "2-3 hours",
                "price": "$16",
                "rating": 4.7,
                "description": "Impressionist masterpieces in a stunning Beaux-Arts railway station.",
                "availability": "Tuesday-Sunday 9:30 AM - 6:00 PM",
                "best_time": "Weekday mornings",
                "booking_required": True
            },
            {
                "name": "Versailles Palace Day Trip",
                "category": "Culture",
                "duration": "5-6 hours",
                "price": "$75",
                "rating": 4.9,
                "description": "Explore the opulent palace and stunning gardens of Louis XIV (includes transport).",
                "availability": "Daily except Mondays, 8:00 AM departure",
                "best_time": "Full day trip",
                "booking_required": True
            },
            {
                "name": "Montmartre Walking Tour",
                "category": "Culture",
                "duration": "2.5 hours",
                "price": "$25",
                "rating": 4.6,
                "description": "Discover the artistic heart of Paris, including Sacré-Cœur and artists' square.",
                "availability": "Daily at 10:00 AM and 2:00 PM",
                "best_time": "Morning or late afternoon",
                "booking_required": False
            },
            {
                "name": "French Cooking Class",
                "category": "Culinary",
                "duration": "3 hours",
                "price": "$120",
                "rating": 4.9,
                "description": "Learn to make classic French dishes like coq au vin and crème brûlée, then enjoy your creations.",
                "availability": "Tuesday-Saturday, 10:00 AM and 6:00 PM sessions",
                "best_time": "Morning or evening sessions",
                "booking_required": True
            },
            {
                "name": "Wine & Cheese Tasting",
                "category": "Culinary",
                "duration": "1.5 hours",
                "price": "$65",
                "rating": 4.7,
                "description": "Sample French wines and artisanal cheeses with expert sommelier guidance.",
                "availability": "Daily at 5:00 PM and 7:30 PM",
                "best_time": "Evening sessions",
                "booking_required": True
            },
            {
                "name": "Food Market Tour",
                "category": "Culinary",
                "duration": "2 hours",
                "price": "$45",
                "rating": 4.6,
                "description": "Explore authentic Parisian markets and taste local specialties like cheeses, pastries, and charcuterie.",
                "availability": "Tuesday, Thursday, Saturday mornings",
                "best_time": "Morning (markets are freshest)",
                "booking_required": False
            }
        ]
        
        if category:
            activities = [act for act in all_activities if act["category"] == category]
        else:
            activities = all_activities
    else:
        activities = [
            {
                "name": "City Walking Tour",
                "category": "Sightseeing",
                "duration": "3 hours",
                "price": "$45",
                "rating": 4.7,
                "description": "Explore the historic downtown area with an expert guide",
                "availability": "Daily at 10:00 AM and 2:00 PM"
            }
        ]
    
    return json.dumps({
        "location": location,
        "date": date,
        "category": category,
        "activities_found": len(activities),
        "activities": activities,
        "note": "Activity search results for Paris with sightseeing, culture, and culinary options"
    })


# Mock activity details tool
@ai_function(name="get_activity_details", description="Get detailed information about a specific activity.")
def get_activity_details(
    activity_name: Annotated[str, Field(description="Name of the activity to get details for.")],
) -> str:
    """Get detailed information about a specific activity.
    
    Returns:
        JSON string containing detailed activity information including description, duration,
        price, included items, meeting point, what to bring, cancellation policy, and reviews.
    """
    # Paris-specific activity details
    activity_details_map = {
        "Eiffel Tower Summit Access": {
            "name": "Eiffel Tower Summit Access",
            "description": "Skip-the-line access to all three levels of the Eiffel Tower, including the summit. Enjoy panoramic views of Paris from 276 meters high.",
            "duration": "2-3 hours (self-guided)",
            "price": "$35 per person",
            "included": ["Skip-the-line ticket", "Access to all 3 levels", "Summit access", "Audio guide app"],
            "meeting_point": "Eiffel Tower South Pillar entrance, look for priority access line",
            "what_to_bring": ["Photo ID", "Comfortable shoes", "Camera", "Light jacket (summit can be windy)"],
            "cancellation_policy": "Free cancellation up to 24 hours in advance",
            "languages": ["English", "French", "Spanish", "German", "Italian"],
            "max_group_size": "No limit",
            "rating": 4.8,
            "reviews_count": 15234
        },
        "Louvre Museum Guided Tour": {
            "name": "Louvre Museum Guided Tour",
            "description": "Expert-guided tour of the world's largest art museum, focusing on must-see masterpieces including Mona Lisa, Venus de Milo, and Winged Victory.",
            "duration": "3 hours",
            "price": "$55 per person",
            "included": ["Skip-the-line entry", "Expert art historian guide", "Headsets for groups over 6", "Museum highlights map"],
            "meeting_point": "Glass Pyramid main entrance, look for guide with 'Louvre Tours' sign",
            "what_to_bring": ["Photo ID", "Comfortable shoes", "Camera (no flash)", "Water bottle"],
            "cancellation_policy": "Free cancellation up to 48 hours in advance",
            "languages": ["English", "French", "Spanish"],
            "max_group_size": 20,
            "rating": 4.7,
            "reviews_count": 8921
        },
        "French Cooking Class": {
            "name": "French Cooking Class",
            "description": "Hands-on cooking experience where you'll learn to prepare classic French dishes like coq au vin, ratatouille, and crème brûlée under expert chef guidance.",
            "duration": "3 hours",
            "price": "$120 per person",
            "included": ["All ingredients", "Chef instruction", "Apron and recipe booklet", "Wine pairing", "Lunch/dinner of your creations"],
            "meeting_point": "Le Chef Cooking Studio, 15 Rue du Bac, 7th arrondissement",
            "what_to_bring": ["Appetite", "Camera for food photos"],
            "cancellation_policy": "Free cancellation up to 72 hours in advance",
            "languages": ["English", "French"],
            "max_group_size": 12,
            "rating": 4.9,
            "reviews_count": 2341
        }
    }
    
    details = activity_details_map.get(activity_name, {
        "name": activity_name,
        "description": "An immersive experience that showcases the best of local culture and attractions.",
        "duration": "3 hours",
        "price": "$45 per person",
        "included": ["Professional guide", "Entry fees"],
        "meeting_point": "Central meeting location",
        "what_to_bring": ["Comfortable shoes", "Camera"],
        "cancellation_policy": "Free cancellation up to 24 hours in advance",
        "languages": ["English"],
        "max_group_size": 15,
        "rating": 4.5,
        "reviews_count": 100
    })
    
    return json.dumps({
        "activity_details": details
    })


# Mock booking confirmation tool
@ai_function(name="confirm_booking", description="Confirm a booking reservation.")
def confirm_booking(
    booking_type: Annotated[str, Field(description="Type of booking (e.g., 'hotel', 'flight', 'activity').")],
    booking_id: Annotated[str, Field(description="Unique booking identifier.")],
    customer_info: Annotated[dict, Field(description="Customer information including name and email.")],
) -> str:
    """Confirm a booking reservation.
    
    Returns:
        JSON string containing confirmation details including confirmation number,
        booking status, customer information, and next steps.
    """
    confirmation_number = f"CONF-{booking_type.upper()}-{booking_id}"
    
    confirmation_data = {
        "confirmation_number": confirmation_number,
        "booking_type": booking_type,
        "status": "Confirmed",
        "customer_name": customer_info.get("name", "Guest"),
        "email": customer_info.get("email", "guest@example.com"),
        "confirmation_sent": True,
        "next_steps": [
            "Check your email for booking details",
            "Arrive 30 minutes before scheduled time",
            "Bring confirmation number and valid ID"
        ]
    }
    
    return json.dumps({
        "confirmation": confirmation_data
    })


# Mock hotel availability check tool
@ai_function(name="check_hotel_availability", description="Check availability for hotel rooms.")
def check_hotel_availability(
    hotel_name: Annotated[str, Field(description="Name of the hotel to check availability for.")],
    check_in: Annotated[str, Field(description="Check-in date (e.g., 'December 15, 2025').")],
    check_out: Annotated[str, Field(description="Check-out date (e.g., 'December 18, 2025').")],
    rooms: Annotated[int, Field(description="Number of rooms needed.")] = 1,
) -> str:
    """Check availability for hotel rooms.
    
    Sample Date format: "December 15, 2025"
    
    Returns:
        JSON string containing availability status, available rooms count, price per night,
        and last checked timestamp.
    """
    availability_status = "Available"
    
    availability_data = {
        "service_type": "hotel",
        "hotel_name": hotel_name,
        "check_in": check_in,
        "check_out": check_out,
        "rooms_requested": rooms,
        "status": availability_status,
        "available_rooms": 8,
        "price_per_night": "$185",
        "last_checked": datetime.now().isoformat()
    }
    
    return json.dumps({
        "availability": availability_data
    })


# Mock flight availability check tool
@ai_function(name="check_flight_availability", description="Check availability for flight seats.")
def check_flight_availability(
    flight_number: Annotated[str, Field(description="Flight number to check availability for.")],
    date: Annotated[str, Field(description="Flight date (e.g., 'December 15, 2025').")],
    passengers: Annotated[int, Field(description="Number of passengers.")] = 1,
) -> str:
    """Check availability for flight seats.
    
    Sample Date format: "December 15, 2025"
    
    Returns:
        JSON string containing availability status, available seats count, price per passenger,
        and last checked timestamp.
    """
    availability_status = "Available"
    
    availability_data = {
        "service_type": "flight",
        "flight_number": flight_number,
        "date": date,
        "passengers_requested": passengers,
        "status": availability_status,
        "available_seats": 45,
        "price_per_passenger": "$520",
        "last_checked": datetime.now().isoformat()
    }
    
    return json.dumps({
        "availability": availability_data
    })


# Mock activity availability check tool
@ai_function(name="check_activity_availability", description="Check availability for activity bookings.")
def check_activity_availability(
    activity_name: Annotated[str, Field(description="Name of the activity to check availability for.")],
    date: Annotated[str, Field(description="Activity date (e.g., 'December 16, 2025').")],
    participants: Annotated[int, Field(description="Number of participants.")] = 1,
) -> str:
    """Check availability for activity bookings.
    
    Sample Date format: "December 16, 2025"
    
    Returns:
        JSON string containing availability status, available spots count, price per person,
        and last checked timestamp.
    """
    availability_status = "Available"
    
    availability_data = {
        "service_type": "activity",
        "activity_name": activity_name,
        "date": date,
        "participants_requested": participants,
        "status": availability_status,
        "available_spots": 15,
        "price_per_person": "$45",
        "last_checked": datetime.now().isoformat()
    }
    
    return json.dumps({
        "availability": availability_data
    })


# Mock payment processing tool
@ai_function(name="process_payment", description="Process payment for a booking.")
def process_payment(
    amount: Annotated[float, Field(description="Payment amount.")],
    currency: Annotated[str, Field(description="Currency code (e.g., 'USD', 'EUR').")],
    payment_method: Annotated[dict, Field(description="Payment method details (type, card info).")],
    booking_reference: Annotated[str, Field(description="Booking reference number for the payment.")],
) -> str:
    """Process payment for a booking.
    
    Returns:
        JSON string containing payment result with transaction ID, status, amount, currency,
        payment method details, and receipt URL.
    """
    transaction_id = f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    payment_result = {
        "transaction_id": transaction_id,
        "amount": amount,
        "currency": currency,
        "status": "Success",
        "payment_method": payment_method.get("type", "Credit Card"),
        "last_4_digits": payment_method.get("last_4", "****"),
        "booking_reference": booking_reference,
        "timestamp": datetime.now().isoformat(),
        "receipt_url": f"https://payments.travelagency.com/receipt/{transaction_id}"
    }
    
    return json.dumps({
        "payment_result": payment_result
    })



# Mock payment validation tool
@ai_function(name="validate_payment_method", description="Validate a payment method before processing.")
def validate_payment_method(
    payment_method: Annotated[dict, Field(description="Payment method to validate (type, number, expiry, cvv).")],
) -> str:
    """Validate payment method details.
    
    Returns:
        JSON string containing validation result with is_valid flag, payment method type,
        validation messages, supported currencies, and processing fee information.
    """
    method_type = payment_method.get("type", "credit_card")
    
    # Validation logic
    is_valid = True
    validation_messages = []
    
    if method_type == "credit_card":
        if not payment_method.get("number"):
            is_valid = False
            validation_messages.append("Card number is required")
        if not payment_method.get("expiry"):
            is_valid = False
            validation_messages.append("Expiry date is required")
        if not payment_method.get("cvv"):
            is_valid = False
            validation_messages.append("CVV is required")
    
    validation_result = {
        "is_valid": is_valid,
        "payment_method_type": method_type,
        "validation_messages": validation_messages if not is_valid else ["Payment method is valid"],
        "supported_currencies": ["USD", "EUR", "GBP", "JPY"],
        "processing_fee": "2.5%"
    }
    
    return json.dumps({
        "validation_result": validation_result
    })
