// Initialize HospitalDB database
db = db.getSiblingDB('HospitalDB');

// Create collections
db.createCollection("hospitals");
db.createCollection("patients");
db.createCollection("products");
db.createCollection("locations");

// Insert sample hospitals
db.hospitals.insertMany([
    {
        _id: ObjectId("507f1f77bcf86cd799439011"),
        nome: "Hospital Municipal Central",
        endereco: "Rua das Flores, 100",
        bairro: "Centro",
        cidade: "São Paulo",
        estado: "SP",
        cep: "01310-100",
        location: {
            type: "Point",
            coordinates: [-46.6333, -23.5505]
        },
        leitos: 250,
        vagasDisponiveis: 45,
        ativo: true
    },
    {
        _id: ObjectId("507f191e810c19729de860ea"),
        nome: "Hospital Geral da Zona Sul",
        endereco: "Av. Paulista, 1578",
        bairro: "Jardins",
        cidade: "São Paulo",
        estado: "SP",
        cep: "01311-000",
        location: {
            type: "Point",
            coordinates: [-46.6388, -23.5489]
        },
        leitos: 180,
        vagasDisponiveis: 30,
        ativo: true
    },
    {
        _id: ObjectId("507f1f77bcf86cd799439012"),
        nome: "Santa Casa de Misericórdia",
        endereco: "Rua da Consolação, 234",
        bairro: "Vila Mariana",
        cidade: "São Paulo",
        estado: "SP",
        cep: "01312-000",
        location: {
            type: "Point",
            coordinates: [-46.6420, -23.5475]
        },
        leitos: 320,
        vagasDisponiveis: 60,
        ativo: true
    }
]);

// Insert sample products (medical supplies)
db.products.insertMany([
    {
        hospitalId: ObjectId("507f1f77bcf86cd799439011"),
        nome: "Paracetamol 500mg",
        descricao: "Analgésico e antitérmico",
        quantidade: 1000,
        tipo: "MEDICAMENTO",
        unidade: "comprimido"
    },
    {
        hospitalId: ObjectId("507f1f77bcf86cd799439011"),
        nome: "Ibuprofeno 600mg",
        descricao: "Anti-inflamatório",
        quantidade: 500,
        tipo: "MEDICAMENTO",
        unidade: "comprimido"
    },
    {
        hospitalId: ObjectId("507f191e810c19729de860ea"),
        nome: "Amoxicilina 500mg",
        descricao: "Antibiótico",
        quantidade: 750,
        tipo: "MEDICAMENTO",
        unidade: "cápsula"
    },
    {
        hospitalId: ObjectId("507f1f77bcf86cd799439012"),
        nome: "Dipirona 500mg",
        descricao: "Analgésico",
        quantidade: 1200,
        tipo: "MEDICAMENTO",
        unidade: "comprimido"
    }
]);

// Insert sample patients
db.patients.insertMany([
    {
        hospitalId: ObjectId("507f1f77bcf86cd799439011"),
        nome: "João Silva",
        cpf: "12345678901",
        genero: "MASCULINO",
        dataNascimento: ISODate("1990-01-15"),
        telefone: "11999887766",
        email: "joao.silva@email.com",
        tipoAtendimento: "EMERGENCIA",
        dataEntrada: ISODate("2024-11-20T10:30:00Z"),
        ativo: true
    },
    {
        hospitalId: ObjectId("507f191e810c19729de860ea"),
        nome: "Maria Santos",
        cpf: "98765432100",
        genero: "FEMININO",
        dataNascimento: ISODate("1985-05-20"),
        telefone: "11988776655",
        email: "maria.santos@email.com",
        tipoAtendimento: "CONSULTA",
        dataEntrada: ISODate("2024-11-21T14:00:00Z"),
        ativo: true
    },
    {
        hospitalId: ObjectId("507f1f77bcf86cd799439011"),
        nome: "Pedro Oliveira",
        cpf: "11122233344",
        genero: "MASCULINO",
        dataNascimento: ISODate("1970-12-10"),
        telefone: "11977665544",
        email: "pedro.oliveira@email.com",
        tipoAtendimento: "INTERNACAO",
        dataEntrada: ISODate("2024-11-19T08:00:00Z"),
        ativo: true
    }
]);

// Insert sample locations (nearby facilities)
db.locations.insertMany([
    {
        nome: "Farmácia São Paulo",
        categoria: "FARMACIA",
        location: {
            type: "Point",
            coordinates: [-46.6350, -23.5510]
        },
        endereco: "Rua Augusta, 500",
        ativo: true
    },
    {
        nome: "Clínica Médica Central",
        categoria: "CLINICA",
        location: {
            type: "Point",
            coordinates: [-46.6400, -23.5495]
        },
        endereco: "Av. Brigadeiro Luís Antônio, 200",
        ativo: true
    },
    {
        nome: "Laboratório de Análises Clínicas",
        categoria: "LABORATORIO",
        location: {
            type: "Point",
            coordinates: [-46.6370, -23.5520]
        },
        endereco: "Rua Estados Unidos, 150",
        ativo: true
    }
]);

// Create geospatial index for location queries
db.hospitals.createIndex({ location: "2dsphere" });
db.locations.createIndex({ location: "2dsphere" });

print("✓ HospitalDB initialized successfully with sample data");
