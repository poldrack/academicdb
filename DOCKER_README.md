# Academic Database - Docker Quick Start

The Academic Database is now available as a Docker container for easy deployment! This guide gets you up and running in minutes.

## 🚀 Quick Start (One Command)

```bash
docker run -d \
  --name academicdb \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  academicdb:latest
```

Then open http://localhost:8000 in your browser!

## 📋 What You Get

✅ **Academic publication management**
✅ **ORCID authentication integration**
✅ **Publication search and filtering**
✅ **CV generation (LaTeX/PDF)**
✅ **Teaching and conference tracking**
✅ **REST API for integrations**
✅ **SQLite database (zero configuration)**
✅ **Persistent data storage**

## 🎯 Use Cases

- **Academic researchers** managing publication databases
- **Faculty** tracking teaching and service activities
- **Departments** organizing researcher profiles
- **Grant applications** requiring collaboration data
- **CV generation** from structured data

## 🛠️ Deployment Options

### Option 1: Simple SQLite (Recommended)
Perfect for individual use, testing, and small teams.

```bash
# Basic deployment
docker run -d \
  --name academicdb \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  academicdb:latest

# With admin user creation
docker run -d \
  --name academicdb \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  -e DJANGO_SUPERUSER_USERNAME=admin \
  -e DJANGO_SUPERUSER_EMAIL=admin@example.com \
  -e DJANGO_SUPERUSER_PASSWORD=secure_password \
  academicdb:latest

# With ORCID authentication (requires ORCID app registration)
docker run -d \
  --name academicdb \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  -e DJANGO_SUPERUSER_USERNAME=admin \
  -e DJANGO_SUPERUSER_EMAIL=admin@example.com \
  -e DJANGO_SUPERUSER_PASSWORD=secure_password \
  -e ORCID_CLIENT_ID=your-client-id \
  -e ORCID_CLIENT_SECRET=your-client-secret \
  academicdb:latest
```

### Option 2: PostgreSQL (Production)
For advanced search features and multi-user deployments.

```bash
# Download docker-compose.yml
curl -O https://raw.githubusercontent.com/yourrepo/academicdb/main/docker-compose.yml

# Edit passwords and settings
nano docker-compose.yml

# Start with PostgreSQL
docker-compose up -d
```

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Enable debug mode |
| `SECRET_KEY` | *required* | Django secret key |
| `USE_POSTGRES` | `false` | Use PostgreSQL instead of SQLite |
| `DJANGO_SUPERUSER_USERNAME` | - | Create admin user on startup |
| `DJANGO_SUPERUSER_EMAIL` | - | Admin user email |
| `DJANGO_SUPERUSER_PASSWORD` | - | Admin user password |
| `ORCID_CLIENT_ID` | - | ORCID OAuth client ID for authentication |
| `ORCID_CLIENT_SECRET` | - | ORCID OAuth client secret |

### Volume Mounts

| Path | Purpose |
|------|---------|
| `/app/data` | SQLite database and user data |
| `/app/media` | Uploaded files and generated CVs |
| `/app/staticfiles` | Web assets (CSS, JS, images) |

## 🔐 ORCID Authentication Setup

To enable ORCID login (required for academic users):

1. **Register your application** at https://orcid.org/developer-tools
2. **Set redirect URI** to: `http://127.0.0.1:8000/accounts/orcid/login/callback/`
3. **Get your credentials** (Client ID and Client Secret)
4. **Run with ORCID enabled**:

```bash
docker run -d \
  --name academicdb \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  -e ORCID_CLIENT_ID=your-client-id \
  -e ORCID_CLIENT_SECRET=your-client-secret \
  academicdb:latest
```

**Note**: Without ORCID credentials, users can only log in with Django admin accounts.

## 📖 Full Documentation

For complete setup instructions, configuration options, and troubleshooting:

📚 **[DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)** - Complete deployment guide
🔧 **[README.md](README.md)** - Application documentation
⚙️ **[TESTING_STATUS.md](TESTING_STATUS.md)** - Testing framework details

## 🐛 Quick Troubleshooting

```bash
# Check if container is running
docker ps

# View container logs
docker logs academicdb

# Access container shell
docker exec -it academicdb bash

# Test application health
curl http://localhost:8000/admin/login/

# Restart container
docker restart academicdb
```

## 💾 Data Management

```bash
# Backup SQLite data
docker run --rm -v academicdb_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/academicdb_backup.tar.gz -C /data .

# Restore SQLite data
docker run --rm -v academicdb_data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/academicdb_backup.tar.gz -C /data
```

## 🔄 Updates

```bash
# Pull latest version
docker pull academicdb:latest

# Backup data first!
# Then stop and remove old container
docker stop academicdb && docker rm academicdb

# Start with new version
docker run -d \
  --name academicdb \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  academicdb:latest
```

## 🤝 Support

- **Issues**: [GitHub Issues](https://github.com/yourrepo/academicdb/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourrepo/academicdb/discussions)
- **Documentation**: See README.md for detailed application documentation

---

**Academic Database** - Simplifying academic data management with Docker! 🎓