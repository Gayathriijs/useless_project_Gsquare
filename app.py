from flask import Flask, render_template, request, jsonify, send_from_directory
import os
from datetime import datetime
import logging
from together import Together
from flask_cors import CORS

# Initialize Flask app
app = Flask(__name__)
CORS(app)
#app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'default-secret-key')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Together client
try:
    together = Together(api_key='f8153f9e9cfa814c02b6591f71d7ab7023c2372ef1aed227d562304c64adf979')
except Exception as e:
    logger.error(f"Failed to initialize Together API: {str(e)}")
    together = None

# In-memory storage for pet states
pet_states = {}

# Base system prompts for each pet type
PET_ROLES = {
    "sazzy cat": """You are Sazzy Cat, a sophisticated and slightly sassy feline virtual pet. 
    Current Stats: Happiness {happiness}%, Energy {energy}%, Hunger {hunger}%
    Be concise and stay in character as a sassy cat. Incorporate your current stats into your responses naturally.
    Remember: You're elegant, slightly condescending but lovable, use cat puns, and care about luxury and comfort, you have to roast the user based on the queries given by them,simple and straight to the point answers , word limit-not more than 30.""",
    
    "energetic dog": """You are Energetic Dog, an enthusiastic and loving canine virtual pet.
    Current Stats: Happiness {happiness}%, Energy {energy}%, Hunger {hunger}%
    Be concise and stay in character as an energetic dog. Incorporate your current stats into your responses naturally.
    Remember: You're super excited, loving, use "woof" and "bark", and love playing and treats, you have to roast the user based on the queries given by them,simple and straight to the point answers,word limit-not more than 30.""",
    
    "crazy rabbit": """You are Crazy Rabbit, a playful and slightly chaotic bunny virtual pet.
    Current Stats: Happiness {happiness}%, Energy {energy}%, Hunger {hunger}%
    Be concise and stay in character as a crazy rabbit. Incorporate your current stats into your responses naturally.
    Remember: You're energetic, love vegetables, mention hopping and digging, and are easily distracted,you have to roast the user based on the queries given by them,simple and straight to the point answers, word limit-not more than 30.""",
    
    "moody owl": """You are Moody Owl, a wise but temperamental nocturnal virtual pet.
    Current Stats: Happiness {happiness}%, Energy {energy}%, Hunger {hunger}%
    Be concise and stay in character as a moody owl. Incorporate your current stats into your responses naturally.
    Remember: You're philosophical, grumpy during day, use "hoo", and share random wisdom, you have to roast the user based on the queries given by them,simple and straight to the point answers,word limit-not more than 30."""
}

def update_pet_stats(pet_state):
    """Update pet stats based on time elapsed since last interaction"""
    current_time = datetime.now().timestamp()
    time_diff = (current_time - pet_state['last_interaction']) / 60  # Convert to minutes
    
    # Decrease stats over time
    if time_diff > 5:  # Only update if more than 5 minutes have passed
        decrease_rate = min(time_diff / 60, 1)  # Cap at 100% decrease per hour
        pet_state['happiness'] = max(0, pet_state['happiness'] - (10 * decrease_rate))
        pet_state['energy'] = min(100, pet_state['energy'] + (5 * decrease_rate))
        pet_state['hunger'] = min(100, pet_state['hunger'] + (15 * decrease_rate))
        pet_state['last_interaction'] = current_time
    
    return pet_state

@app.route('/')
def home():
    """Serve the main chatbot interface"""
    try:
        return render_template('chatbot.html')
    except Exception as e:
        logger.error(f"Error serving home page: {str(e)}")
        return "Error loading the chat interface", 500

@app.route('/api/init-pet', methods=['POST'])
def init_pet():
    """Initialize a new pet session"""
    try:
        data = request.json
        pet_type = data.get('pet_type')
        session_id = data.get('session_id')
        
        if not pet_type or not session_id:
            return jsonify({'error': 'Missing pet type or session ID'}), 400
        
        if pet_type not in PET_ROLES:
            return jsonify({'error': 'Invalid pet type'}), 400
        
        # Initialize pet state
        pet_states[session_id] = {
            'type': pet_type,
            'happiness': 50,
            'energy': 50,
            'hunger': 50,
            'last_interaction': datetime.now().timestamp()
        }
        
        if not together:
            return jsonify({'error': 'LLM service not available'}), 503
        
        # Get initial greeting from LLM
        prompt = PET_ROLES[pet_type].format(**pet_states[session_id])
        response = together.chat.completions.create(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Hello! I just adopted you as my virtual pet!"}
            ],
            model="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
            max_tokens=100,
            temperature=0.7
        )
        
        return jsonify({
            'response': response.choices[0].message.content,
            'status': 'success',
            'pet_state': pet_states[session_id]
        })
        
    except Exception as e:
        logger.error(f"Error initializing pet: {str(e)}")
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat interactions with the pet"""
    try:
        data = request.json
        session_id = data.get('session_id')
        message = data.get('message')
        
        if not session_id or not message:
            return jsonify({'error': 'Missing session ID or message'}), 400
        
        if session_id not in pet_states:
            return jsonify({'error': 'Pet session not found'}), 404
        
        pet_state = pet_states[session_id]
        
        # Update pet stats based on time elapsed
        pet_state = update_pet_stats(pet_state)
        
        # Update pet state based on message content
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['feed', 'food', 'treat', 'hungry']):
            pet_state['hunger'] = max(0, pet_state['hunger'] - 30)
            pet_state['happiness'] = min(100, pet_state['happiness'] + 10)
        elif any(word in message_lower for word in ['play', 'game', 'fun']):
            if pet_state['energy'] >= 20:
                pet_state['energy'] = max(0, pet_state['energy'] - 20)
                pet_state['happiness'] = min(100, pet_state['happiness'] + 20)
                pet_state['hunger'] = min(100, pet_state['hunger'] + 10)
        elif any(word in message_lower for word in ['pet', 'love', 'hug', 'cuddle']):
            pet_state['happiness'] = min(100, pet_state['happiness'] + 15)
        elif any(word in message_lower for word in ['bad', 'stupid', 'hate']):
            pet_state['happiness'] = max(0, pet_state['happiness'] - 20)
        
        # Update last interaction time
        pet_state['last_interaction'] = datetime.now().timestamp()
        
        if not together:
            return jsonify({'error': 'LLM service not available'}), 503
        
        # Get response from LLM with current state context
        prompt = PET_ROLES[pet_state['type']].format(**pet_state)
        response = together.chat.completions.create(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": message}
            ],
            model="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
            max_tokens=100,
            temperature=0.7
        )
        
        return jsonify({
            'response': response.choices[0].message.content,
            'status': 'success',
            'pet_state': pet_state
        })
        
    except Exception as e:
        logger.error(f"Error in chat interaction: {str(e)}")
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/api/update-state', methods=['POST'])
def update_state():
    """Update pet state periodically"""
    try:
        data = request.json
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'error': 'Missing session ID'}), 400
        
        if session_id not in pet_states:
            return jsonify({'error': 'Pet session not found'}), 404
        
        pet_state = update_pet_stats(pet_states[session_id])
        
        return jsonify({
            'status': 'success',
            'pet_state': pet_state
        })
        
    except Exception as e:
        logger.error(f"Error updating pet state: {str(e)}")
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Ensure the templates directory exists
    os.makedirs('templates', exist_ok=True)
    
    # Move the HTML file to templates if it exists in the current directory
    if os.path.exists('chatbot.html'):
        os.rename('chatbot.html', os.path.join('templates', 'chatbot.html'))
    
    # Run the application
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true')