import logging
from datetime import datetime, timezone
import json

logging.basicConfig(level=logging.DEBUG)

class Item:
    def __init__(self, data):
        logging.debug(f"Initializing Item with raw data keys: {list(data.keys())}")
        self.raw_data = data

        self.id = data.get("id", "Unknown ID")
        self.title = data.get("title", "No title provided")
        self.price = data.get("price", "Unknown price")
        self.currency = data.get("currency", "Unknown currency")
        self.brand_title = data.get("brand_title", "Unknown brand")
        self.size_title = data.get("size_title", "Unknown size")
        self.url = data.get("url", "No URL provided")

        # Handle photo data
        self.photo_url = data.get("photo", {}).get("url", "No photo URL")

        # Extract description using the enhanced approach
        self.description = self._extract_description(data)
        
        # Add field for RapidAPI description
        self.rapid_api_description = None

        # Handle created_at timestamp
        self.created_at_ts = self._parse_timestamp(data)
        
        self.status = data.get("status", "Unknown status")

        # Extract user feedback data
        self.user_feedback = self._extract_user_feedback(data)

    def update_description_from_rapid_api(self, rapid_api_description):
        """
        Updates the item's description with data from RapidAPI.
        
        Args:
            rapid_api_description (str): The description fetched from RapidAPI
        """
        if rapid_api_description:
            self.rapid_api_description = rapid_api_description
            logging.debug(f"Updated RapidAPI description for item {self.id}")

    def get_description(self):
        """
        Returns the best available description, preferring RapidAPI description if available.
        
        Returns:
            str: The item description from the best available source
        """
        return self.rapid_api_description if self.rapid_api_description else self.description

    def _extract_description(self, data):
        """
        Extracts a description from various potential locations in the data.
        
        Args:
            data (dict): The raw data containing item information.
        
        Returns:
            str: The found description or a default message if none is found.
        """
        description_candidates = []

        # Direct description field
        if "description" in data:
            description_candidates.append(data["description"])

        # Check for description in 'item_box'
        item_box = data.get("item_box", {})
        if "description" in item_box:
            description_candidates.append(item_box["description"])
            logging.debug("Description found in item_box.")

        # Check for description in 'props.pageProps.itemDto'
        item_dto = data.get("props", {}).get("pageProps", {}).get("itemDto", {})
        if "description" in item_dto:
            description_candidates.append(item_dto["description"])
            logging.debug("Description found in itemDto.")

        # Check for nested description sections
        sections = data.get("sections", [])
        for section in sections:
            if section.get("name") == "description":
                section_description = section.get("data", {}).get("description")
                if section_description:
                    description_candidates.append(section_description)
                    logging.debug("Description found in 'data' under 'name': 'description'.")

        # Return the first valid description or a default message
        for description in description_candidates:
            if description and description.strip():
                return description.strip()

        logging.warning("No description found in provided data, item_box, or nested structures.")
        return "No description provided"

    def _extract_user_feedback(self, data):
        """
        Extracts user feedback information from the raw data.
        
        Args:
            data (dict): The raw data containing user feedback.
        
        Returns:
            dict: A dictionary containing feedback counts.
        """
        feedback = {}
        user_data = data.get("user", {})

        feedback['positive_feedback_count'] = user_data.get("positive_feedback_count", 0)
        feedback['neutral_feedback_count'] = user_data.get("neutral_feedback_count", 0)
        feedback['negative_feedback_count'] = user_data.get("negative_feedback_count", 0)

        return feedback

    def _parse_timestamp(self, data):
        """
        Parse timestamp from data in various formats.
        
        Args:
            data (dict): The raw data containing timestamp information.
            
        Returns:
            datetime: The parsed timestamp or current time if parsing fails.
        """
        try:
            # Try getting timestamp from photo high_resolution
            timestamp = data.get("photo", {}).get("high_resolution", {}).get("timestamp")
            if timestamp:
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)

            # Try getting timestamp from created_at_ts field
            created_at = data.get("created_at_ts")
            if created_at:
                if isinstance(created_at, (int, float)):
                    return datetime.fromtimestamp(created_at, tz=timezone.utc)
                elif isinstance(created_at, str):
                    try:
                        return datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    except ValueError:
                        pass

            # Try parsing from last_loged_on_ts
            last_logged = data.get("last_loged_on_ts")
            if last_logged:
                try:
                    return datetime.fromisoformat(last_logged.replace('Z', '+00:00'))
                except ValueError:
                    pass

        except (ValueError, TypeError) as e:
            logging.error(f"Error parsing timestamp for item {self.id}: {e}")

        logging.warning(f"No valid timestamp found for item {self.id}. Using current time.")
        return datetime.now(timezone.utc)

    def __str__(self):
        """
        Return a string representation of the Item.
        
        Returns:
            str: A formatted string containing basic item information.
        """
        return f"Item(id={self.id}, title={self.title}, price={self.price} {self.currency})"

    def __repr__(self):
        """
        Return a detailed string representation of the Item.
        
        Returns:
            str: A detailed string representation of the item's attributes.
        """
        return (f"Item(id={self.id}, title={self.title}, price={self.price}, "
                f"currency={self.currency}, brand={self.brand_title}, "
                f"size={self.size_title}, status={self.status})")