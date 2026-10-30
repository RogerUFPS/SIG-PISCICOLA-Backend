url="localhost:8000/api"
email=maxiservicios198@gmail.com
password=maxi12345
#email=keylersneiderac@ufps.edu.co
#password=unKeylersito

response=$(http --check-status --ignore-stdin POST "${url}/auth/login/" \
	email="$email" password="$password")

jwt=$(printf '%s' "$response" | jq -r '.tokens.access')

http -A bearer -a "$jwt" GET "${url}/farms/20/ponds/"
